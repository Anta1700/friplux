-- ============================================================
-- Frip'Lux : script 007
-- Stock de balles par dépôt et transferts entre dépôts.
--
-- Les balles d'un même lot peuvent être réparties entre plusieurs dépôts
-- (ex. lot 000001 : 5 balles au Dépôt principal, 4 à Thiaroye).
-- Le stock d'un dépôt se calcule à partir de mouvements_stock :
--   RECEPTION_BALLE   : balle scannée à la réception           -> + dépôt d'arrivée
--   TRANSFERT_BALLES  : envoi d'un dépôt à un autre             -> - dépôt de départ dès l'envoi,
--                       + dépôt d'arrivée au fur et à mesure des balles scannées à l'arrivée
-- (les ventes sont déduites directement des lignes de vente).
--
-- - mouvements_stock.balles         : nombre de balles du mouvement
-- - mouvements_stock.balles_recues  : balles d'un transfert scannées à l'arrivée
-- - mouvements_stock.transfert_id   : transfert auquel appartient le mouvement
-- Les valeurs autorisées existantes sont CONSERVÉES : les nouvelles y sont ajoutées.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/007_stock_balles_depots.sql
-- ============================================================

ALTER TABLE mouvements_stock ADD COLUMN IF NOT EXISTS balles        integer;
ALTER TABLE mouvements_stock ADD COLUMN IF NOT EXISTS balles_recues integer;
ALTER TABLE mouvements_stock ADD COLUMN IF NOT EXISTS transfert_id  bigint;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_mouvements_transfert') THEN
        ALTER TABLE mouvements_stock ADD CONSTRAINT fk_mouvements_transfert
            FOREIGN KEY (transfert_id) REFERENCES transferts_stock(id) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_mouvements_lot_type ON mouvements_stock (lot_id, type_mouvement);
CREATE INDEX IF NOT EXISTS idx_mouvements_transfert ON mouvements_stock (transfert_id);

-- Remplace les contraintes CHECK des colonnes concernées, en gardant toutes les valeurs déjà utilisées.
DO $$
DECLARE
    r record;
    valeurs text;
BEGIN
    FOR r IN
        SELECT DISTINCT c.conname, c.conrelid::regclass::text AS tbl
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.contype = 'c'
          AND (c.conrelid::regclass::text, a.attname::text) IN (
                ('mouvements_stock', 'type_mouvement'),
                ('mouvements_stock', 'statut'),
                ('mouvements_stock', 'quantite_pieces'),
                ('mouvements_stock', 'poids_kg'),
                ('mouvements_stock', 'balles'),
                ('mouvements_stock', 'balles_recues'),
                ('transferts_stock', 'statut'))
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
    END LOOP;

    SELECT string_agg(quote_literal(v), ', ') INTO valeurs FROM (
        SELECT unnest(ARRAY['RECEPTION_BALLE', 'TRANSFERT_BALLES', 'ENTREE', 'SORTIE', 'TRANSFERT', 'AJUSTEMENT']) AS v
        UNION SELECT DISTINCT type_mouvement FROM mouvements_stock) x;
    EXECUTE format('ALTER TABLE mouvements_stock ADD CONSTRAINT chk_mouvements_type CHECK (type_mouvement IN (%s))', valeurs);

    SELECT string_agg(quote_literal(v), ', ') INTO valeurs FROM (
        SELECT unnest(ARRAY['VALIDE', 'EN_TRANSIT', 'RECU', 'ANNULE']) AS v
        UNION SELECT DISTINCT statut FROM mouvements_stock) x;
    EXECUTE format('ALTER TABLE mouvements_stock ADD CONSTRAINT chk_mouvements_statut CHECK (statut IN (%s))', valeurs);

    SELECT string_agg(quote_literal(v), ', ') INTO valeurs FROM (
        SELECT unnest(ARRAY['BROUILLON', 'EN_COURS', 'RECU', 'RECU_AVEC_ECART', 'ANNULE']) AS v
        UNION SELECT DISTINCT statut FROM transferts_stock) x;
    EXECUTE format('ALTER TABLE transferts_stock ADD CONSTRAINT chk_transferts_statut CHECK (statut IN (%s))', valeurs);
END $$;

ALTER TABLE mouvements_stock ADD CONSTRAINT chk_mouvements_quantites
    CHECK (quantite_pieces >= 0 AND poids_kg >= 0);
ALTER TABLE mouvements_stock ADD CONSTRAINT chk_mouvements_balles
    CHECK ((balles IS NULL OR balles > 0)
           AND (balles_recues IS NULL OR (balles_recues >= 0 AND (balles IS NULL OR balles_recues <= balles))));
