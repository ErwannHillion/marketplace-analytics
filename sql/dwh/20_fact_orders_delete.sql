-- Premiere moitie du pattern DELETE + INSERT : vide la partition traitee.
DELETE FROM dwh.fact_orders
WHERE dt = %(dt)s::date
