-- ============================================================
-- Frip'Lux : script 009
-- Numéro de carte d'identité du client (facultatif), saisi au moment de la vente.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/009_client_piece_identite.sql
-- ============================================================

ALTER TABLE clients ADD COLUMN IF NOT EXISTS numero_piece_identite varchar(50);
CREATE INDEX IF NOT EXISTS ix_clients_numero_piece_identite ON clients (numero_piece_identite);
