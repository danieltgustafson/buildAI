-- Metabase-friendly views for Contractor Ops AI
-- These are created after Alembic migrations run.
-- Run manually: psql -f sql/views.sql  OR  auto-loaded via docker-compose init script.

-- v_job_cost_summary: planned vs actual per job
CREATE OR REPLACE VIEW v_job_cost_summary AS
SELECT
    j.job_id,
    j.job_name,
    j.customer_name,
    j.status,
    j.contract_value,
    -- budget (latest version)
    b.planned_labor_hours,
    b.planned_labor_cost,
    b.planned_material_cost,
    b.planned_sub_cost,
    COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0) AS planned_total_cost,
    -- actuals
    COALESCE(t.actual_labor_hours, 0) AS actual_labor_hours,
    COALESCE(t.actual_labor_cost, 0) AS actual_labor_cost,
    COALESCE(g.actual_nonlabor_cost, 0) AS actual_nonlabor_cost,
    COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0) AS actual_total_cost,
    -- billing
    COALESCE(bi.billed_to_date, 0) AS billed_to_date,
    -- margin
    CASE WHEN COALESCE(bi.billed_to_date, 0) > 0
        THEN ROUND(((bi.billed_to_date - (COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0))) / bi.billed_to_date * 100)::numeric, 2)
        ELSE NULL
    END AS margin_pct
FROM jobs j
LEFT JOIN LATERAL (
    SELECT planned_labor_hours, planned_labor_cost, planned_material_cost, planned_sub_cost
    FROM job_budgets
    WHERE job_id = j.job_id
    ORDER BY budget_version DESC
    LIMIT 1
) b ON true
LEFT JOIN LATERAL (
    SELECT SUM(hours) AS actual_labor_hours, SUM(labor_cost_burdened) AS actual_labor_cost
    FROM time_entries
    WHERE job_id = j.job_id
) t ON true
LEFT JOIN LATERAL (
    SELECT SUM(amount) AS actual_nonlabor_cost
    FROM gl_transactions
    WHERE job_id = j.job_id
) g ON true
LEFT JOIN LATERAL (
    SELECT SUM(amount_billed) AS billed_to_date
    FROM job_billing
    WHERE job_id = j.job_id
) bi ON true;


-- v_wip_report: WIP / earned value per active job
CREATE OR REPLACE VIEW v_wip_report AS
SELECT
    j.job_id,
    j.job_name,
    j.customer_name,
    j.contract_value,
    COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0) AS actual_total_cost,
    COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0) AS budget_total_cost,
    CASE
        WHEN (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0)) > 0
        THEN LEAST(
            (COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0))::numeric
            / (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0))::numeric,
            1.2
        )
        ELSE NULL
    END AS pct_complete,
    CASE
        WHEN (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0)) > 0
            AND j.contract_value IS NOT NULL
        THEN LEAST(
            (COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0))::numeric
            / (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0))::numeric,
            1.2
        ) * j.contract_value
        ELSE NULL
    END AS earned_revenue,
    COALESCE(bi.billed_to_date, 0) AS billed_to_date,
    CASE
        WHEN (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0)) > 0
            AND j.contract_value IS NOT NULL
        THEN COALESCE(bi.billed_to_date, 0) - (
            LEAST(
                (COALESCE(t.actual_labor_cost, 0) + COALESCE(g.actual_nonlabor_cost, 0))::numeric
                / (COALESCE(b.planned_labor_cost, 0) + COALESCE(b.planned_material_cost, 0) + COALESCE(b.planned_sub_cost, 0))::numeric,
                1.2
            ) * j.contract_value
        )
        ELSE NULL
    END AS over_under_billing,
    j.status
FROM jobs j
LEFT JOIN LATERAL (
    SELECT planned_labor_hours, planned_labor_cost, planned_material_cost, planned_sub_cost
    FROM job_budgets
    WHERE job_id = j.job_id
    ORDER BY budget_version DESC
    LIMIT 1
) b ON true
LEFT JOIN LATERAL (
    SELECT SUM(hours) AS actual_labor_hours, SUM(labor_cost_burdened) AS actual_labor_cost
    FROM time_entries
    WHERE job_id = j.job_id
) t ON true
LEFT JOIN LATERAL (
    SELECT SUM(amount) AS actual_nonlabor_cost
    FROM gl_transactions
    WHERE job_id = j.job_id
) g ON true
LEFT JOIN LATERAL (
    SELECT SUM(amount_billed) AS billed_to_date
    FROM job_billing
    WHERE job_id = j.job_id
) bi ON true
WHERE j.status = 'active';


-- v_exceptions: open exceptions for dashboarding
CREATE OR REPLACE VIEW v_exceptions AS
SELECT
    e.exception_id,
    e.job_id,
    j.job_name,
    e.type,
    e.severity,
    e.message,
    e.source_ref,
    e.created_at,
    e.resolved_at
FROM exceptions e
LEFT JOIN jobs j ON j.job_id = e.job_id
ORDER BY e.created_at DESC;
