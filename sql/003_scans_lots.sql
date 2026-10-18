-- ============================================================
-- Frip'Lux : script 003
-- Historique des scans de balles.
--
-- Chaque lecture d'un QR code (ou saisie d'un code) crée une ligne.
-- Les compteurs sont CALCULÉS à partir de cet historique (jamais saisis à la main) :
--   - nombre total de scans          = nombre de lignes
--   - nombre de balles uniques       = nombre de lot_id distincts
--
-- La catégorie est copiée au moment du scan : si une balle est reclassée plus tard,
-- les statistiques passées restent exactes.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/003_scans_lots.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS scans_lots (
    id                bigserial     PRIMARY KEY,
    date_scan         timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    code_scanne       varchar(100)  NOT NULL,
    resultat          varchar(20)   NOT NULL,
    lot_id            bigint,
    qr_code_id        bigint,
    categorie_lot_id  bigint,
    utilisateur_id    bigint,
    depot_id          bigint,
    CONSTRAINT chk_scans_resultat CHECK (resultat IN ('OK', 'QR_REMPLACE', 'INCONNU')),
    CONSTRAINT chk_scans_lot_si_trouve CHECK (resultat = 'INCONNU' OR lot_id IS NOT NULL),
    CONSTRAINT fk_scans_lot FOREIGN KEY (lot_id)
        REFERENCES lots(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_scans_qr_code FOREIGN KEY (qr_code_id)
        REFERENCES qr_codes(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_scans_categorie FOREIGN KEY (categorie_lot_id)
        REFERENCES categories_lots(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_scans_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_scans_depot FOREIGN KEY (depot_id)
        REFERENCES depots(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_scans_date            ON scans_lots (date_scan);
CREATE INDEX IF NOT EXISTS idx_scans_lot             ON scans_lots (lot_id);
CREATE INDEX IF NOT EXISTS idx_scans_categorie_date  ON scans_lots (categorie_lot_id, date_scan);
CREATE INDEX IF NOT EXISTS idx_scans_utilisateur     ON scans_lots (utilisateur_id);
