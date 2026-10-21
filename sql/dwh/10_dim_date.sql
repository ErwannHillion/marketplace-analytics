-- Calendrier 2024-2027, etendu si la date traitee sort de cette plage.
-- ON CONFLICT DO NOTHING : une date deja presente n'est jamais reecrite.
-- Bornes en timestamp sans fuseau : avec des dates nues, generate_series
-- renverrait un timestamptz et le calendrier dependrait du fuseau de session.
INSERT INTO dwh.dim_date (dt, year, quarter, month, day, iso_week, day_of_week, is_weekend)
SELECT d::date,
       EXTRACT(YEAR FROM d)::int,
       EXTRACT(QUARTER FROM d)::int,
       EXTRACT(MONTH FROM d)::int,
       EXTRACT(DAY FROM d)::int,
       EXTRACT(WEEK FROM d)::int,
       EXTRACT(ISODOW FROM d)::int,
       EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(
         LEAST(DATE '2024-01-01', %(dt)s::date)::timestamp,
         GREATEST(DATE '2027-12-31', %(dt)s::date)::timestamp,
         INTERVAL '1 day'
     ) AS d
ON CONFLICT (dt) DO NOTHING
