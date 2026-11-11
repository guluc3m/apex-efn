-- Savings reported by each recommendation (integer minor units per unit; null when no reference existed).
select
    tenant_id,
    mission_id,
    toDate(generated_at) as day,
    JSONExtract(savings, 'vs_list_price_eur_minor', 'Nullable(Int64)') as vs_list_price_eur_minor,
    JSONExtract(savings, 'vs_market_median_eur_minor', 'Nullable(Int64)') as vs_market_median_eur_minor
from {{ source('apex_pg', 'recommendations') }}
