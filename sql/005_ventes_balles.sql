-- ============================================================
-- Frip'Lux : script 005
-- Ventes de balles entières, facture automatique, paiements et moratoires.
--
-- - Une ligne de vente = N balles d'un même lot (lignes_vente.lot_id, unité « BALLE »).
-- - Prix de vente conseillé par balle (FCFA) : sur la référence fournisseur
--   (s'applique à tous les lots de cette référence) et/ou sur le lot lui-même.
--   Le vendeur peut le négocier ; l'écart est gardé dans lignes_vente.remise.
-- - Les valeurs autorisées des statuts et des moyens de paiement sont (re)définies ici :
--   les anciennes contraintes CHECK de ces colonnes sont remplacées.
-- - montant_ligne est désormais écrit par l'application (s'il était calculé par la base,
--   le calcul est retiré pour éviter les conflits).
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- Si des données existantes ne respectent pas les nouvelles règles, le script échoue
-- et AUCUNE modification n'est conservée.
-- À appliquer avec : python manage.py appliquer_sql sql/005_ventes_balles.sql
-- ============================================================

-- 1. Prix de vente conseillé par balle
ALTER TABLE references_fournisseurs ADD COLUMN IF NOT EXISTS prix_vente_balle numeric(15,2);
ALTER TABLE lots                    ADD COLUMN IF NOT EXISTS prix_vente_balle numeric(15,2);

-- 2. Lignes de vente : lot vendu, prix conseillé au moment de la vente
ALTER TABLE lignes_vente ADD COLUMN IF NOT EXISTS lot_id bigint;
ALTER TABLE lignes_vente ADD COLUMN IF NOT EXISTS prix_conseille numeric(15,2);
ALTER TABLE lignes_vente ALTER COLUMN categorie_produit_id DROP NOT NULL;   -- un lot n'a pas toujours de sous-catégorie

DO $$
BEGIN
    -- montant_ligne calculé par la base -> colonne normale
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'lignes_vente' AND column_name = 'montant_ligne' AND is_generated = 'ALWAYS') THEN
        ALTER TABLE lignes_vente ALTER COLUMN montant_ligne DROP EXPRESSION;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lignes_vente_lot') THEN
        ALTER TABLE lignes_vente ADD CONSTRAINT fk_lignes_vente_lot
            FOREIGN KEY (lot_id) REFERENCES lots(id) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_lignes_vente_lot ON lignes_vente (lot_id);
CREATE INDEX IF NOT EXISTS idx_ventes_vendeur_statut ON ventes (vendeur_id, statut);
CREATE INDEX IF NOT EXISTS idx_paiements_vente ON paiements (vente_id);
CREATE INDEX IF NOT EXISTS idx_clients_telephone ON clients (telephone);

-- 3. Remplacement des contraintes CHECK des colonnes de statut / mode / unité / type
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT DISTINCT c.conname, c.conrelid::regclass::text AS tbl
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.contype = 'c'
          AND (c.conrelid::regclass::text, a.attname::text) IN (
                ('ventes', 'statut'),
                ('lignes_vente', 'unite_vente'),
                ('lignes_vente', 'remise'),
                ('factures', 'statut'),
                ('paiements', 'mode_paiement'),
                ('paiements', 'statut'),
                ('moratoires', 'type_moratoire'),
                ('moratoires', 'statut'),
                ('echeances_moratoire', 'statut'),
                ('clients', 'type_client'))
    LOOP
        RAISE NOTICE 'Contrainte remplacée : %.%', r.tbl, r.conname;
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
    END LOOP;
END $$;

ALTER TABLE ventes ADD CONSTRAINT chk_ventes_statut
    CHECK (statut IN ('BROUILLON', 'VALIDEE', 'ANNULEE'));
ALTER TABLE lignes_vente ADD CONSTRAINT chk_lignes_vente_unite
    CHECK (unite_vente IN ('BALLE', 'KG', 'PIECE'));
ALTER TABLE lignes_vente ADD CONSTRAINT chk_lignes_vente_remise
    CHECK (remise >= 0);
ALTER TABLE factures ADD CONSTRAINT chk_factures_statut
    CHECK (statut IN ('EMISE', 'PAYEE', 'ANNULEE'));
ALTER TABLE paiements ADD CONSTRAINT chk_paiements_mode
    CHECK (mode_paiement IN ('ESPECES', 'WAVE', 'ORANGE_MONEY', 'VIREMENT', 'CHEQUE'));
ALTER TABLE paiements ADD CONSTRAINT chk_paiements_statut
    CHECK (statut IN ('VALIDE', 'ANNULE'));
ALTER TABLE moratoires ADD CONSTRAINT chk_moratoires_type
    CHECK (type_moratoire IN ('ECHEANCIER'));
ALTER TABLE moratoires ADD CONSTRAINT chk_moratoires_statut
    CHECK (statut IN ('EN_COURS', 'SOLDE', 'ANNULE'));
ALTER TABLE echeances_moratoire ADD CONSTRAINT chk_echeances_statut
    CHECK (statut IN ('A_PAYER', 'PARTIELLE', 'PAYEE', 'ANNULEE'));
ALTER TABLE clients ADD CONSTRAINT chk_clients_type
    CHECK (type_client IN ('PARTICULIER', 'PROFESSIONNEL'));

-- 4. Prix positifs
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_lots_prix_vente_balle') THEN
        ALTER TABLE lots ADD CONSTRAINT chk_lots_prix_vente_balle CHECK (prix_vente_balle IS NULL OR prix_vente_balle >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_references_prix_vente_balle') THEN
        ALTER TABLE references_fournisseurs ADD CONSTRAINT chk_references_prix_vente_balle
            CHECK (prix_vente_balle IS NULL OR prix_vente_balle >= 0);
    END IF;
END $$;
