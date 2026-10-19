-- ============================================================
-- Frip'Lux : script 004
-- Un lot = une ligne de la fiche fournisseur, qui peut regrouper plusieurs balles
-- (ex. FRPLX-LOT-2026-000001 = 9 balles « Articles de déstockage été »).
-- Les balles d'un même lot partagent le même code et le même QR code.
--
-- - nombre_balles        : balles annoncées par le fournisseur pour ce lot
-- - nombre_balles_recues : balles effectivement comptées à la réception (vide tant que non reçu)
-- - poids_kg et prix_achat du lot deviennent les TOTAUX du lot.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/004_nombre_balles_lot.sql
-- ============================================================

ALTER TABLE lots ADD COLUMN IF NOT EXISTS nombre_balles        integer NOT NULL DEFAULT 1;
ALTER TABLE lots ADD COLUMN IF NOT EXISTS nombre_balles_recues integer;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_lots_nombre_balles') THEN
        ALTER TABLE lots ADD CONSTRAINT chk_lots_nombre_balles CHECK (nombre_balles > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_lots_nombre_balles_recues') THEN
        ALTER TABLE lots ADD CONSTRAINT chk_lots_nombre_balles_recues
            CHECK (nombre_balles_recues IS NULL OR nombre_balles_recues >= 0);
    END IF;
END $$;
