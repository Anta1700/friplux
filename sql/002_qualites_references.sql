-- ============================================================
-- Frip'Lux : script 002
-- Qualités, références fournisseurs, sous-catégories et
-- trois nouvelles colonnes (facultatives) sur les lots.
--
-- - Ne supprime aucune donnée.
-- - Peut être relancé sans risque (idempotent).
-- - À appliquer avec : python manage.py appliquer_sql sql/002_qualites_references.sql
--   (tout s'exécute dans une seule transaction : en cas d'erreur, rien n'est modifié).
-- ============================================================


-- ------------------------------------------------------------
-- 1. Qualités
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qualites (
    id          bigserial    PRIMARY KEY,
    code        varchar(30)  NOT NULL UNIQUE,
    nom         varchar(80)  NOT NULL UNIQUE,
    ordre       integer      NOT NULL DEFAULT 0,
    actif       boolean      NOT NULL DEFAULT true,
    CONSTRAINT chk_qualites_code_non_vide CHECK (length(trim(code)) > 0)
);

INSERT INTO qualites (code, nom, ordre) VALUES
    ('CREME',          'Crème',          1),
    ('PREMIER_CHOIX',  'Premier choix',  2),
    ('DEUXIEME_CHOIX', 'Deuxième choix', 3),
    ('DESTOCKAGE',     'Déstockage',     4),
    ('CHIFFONS',       'Chiffons',       5)
ON CONFLICT DO NOTHING;


-- ------------------------------------------------------------
-- 2. Catégorie « Accessoires » (les 5 autres existent déjà)
-- ------------------------------------------------------------
INSERT INTO categories_lots (code, nom, description, actif)
VALUES ('ACCESSOIRES', 'Accessoires', 'Chaussures, sacs, ceintures, casquettes, foulards, cuir', true)
ON CONFLICT DO NOTHING;


-- ------------------------------------------------------------
-- 3. Sous-catégories (table categories_produits)
--    Les catégories principales sont les lignes sans parent.
-- ------------------------------------------------------------
INSERT INTO categories_produits (code, nom, parent_id, actif) VALUES
    ('MIXTE',       'Mixte',       NULL, true),
    ('ACCESSOIRES', 'Accessoires', NULL, true)
ON CONFLICT DO NOTHING;

-- Renommages des sous-catégories existantes
UPDATE categories_produits SET nom = 'Chemisiers'           WHERE code = 'FEMME_CHEMISES';
UPDATE categories_produits SET nom = 'Vêtements assortis'   WHERE code = 'BEBE_VETEMENTS';
UPDATE categories_produits SET nom = 'Tissus d''ameublement' WHERE code = 'TAPISSERIE_TISSUS';

-- Sous-catégories mal placées : désactivées (pas supprimées).
-- Les chaussures et sacs vont dans Accessoires.
UPDATE categories_produits SET actif = false
WHERE code IN ('HOMME_CHAUSSURES', 'FEMME_CHAUSSURES', 'BEBE_CHAUSSURES', 'FEMME_SACS');

-- Nouvelles sous-catégories : (code, nom, code du parent)
INSERT INTO categories_produits (code, nom, parent_id, actif)
SELECT n.code, n.nom, p.id, true
FROM (VALUES
    ('HOMME_JEANS',               'Jeans',                 'HOMME'),
    ('HOMME_SHORTS',              'Shorts',                'HOMME'),
    ('HOMME_POLOS',               'Polos',                 'HOMME'),
    ('HOMME_ENSEMBLES',           'Ensembles',             'HOMME'),

    ('FEMME_JUPES',               'Jupes',                 'FEMME'),
    ('FEMME_JEANS',               'Jeans',                 'FEMME'),
    ('FEMME_LEGGINGS',            'Leggings',              'FEMME'),
    ('FEMME_POLOS',               'Polos',                 'FEMME'),
    ('FEMME_VESTES',              'Vestes',                'FEMME'),
    ('FEMME_LINGERIE',            'Lingerie',              'FEMME'),
    ('FEMME_TENDANCE',            'Tendance',              'FEMME'),

    ('BEBE_PANTALONS',            'Pantalons',             'BEBE'),
    ('BEBE_JEANS',                'Jeans',                 'BEBE'),
    ('BEBE_SURVETEMENTS',         'Survêtements',          'BEBE'),
    ('BEBE_GARCON',               'Garçon',                'BEBE'),

    ('MIXTE_SOUS_VETEMENTS',      'Sous-vêtements',        'MIXTE'),
    ('MIXTE_MAILLOTS',            'Maillots de bain',      'MIXTE'),
    ('MIXTE_SPORT',               'Sport',                 'MIXTE'),
    ('MIXTE_SURVETEMENTS',        'Survêtements',          'MIXTE'),
    ('MIXTE_VESTES_JEAN',         'Vestes en jean',        'MIXTE'),
    ('MIXTE_IMPERMEABLES',        'Imperméables',          'MIXTE'),
    ('MIXTE_NUIT',                'Nuit et pyjamas',       'MIXTE'),
    ('MIXTE_CHAUSSETTES',         'Chaussettes',           'MIXTE'),
    ('MIXTE_CHEMISES_FLANELLE',   'Chemises flanelle',     'MIXTE'),
    ('MIXTE_TRAVAIL',             'Vêtements de travail',  'MIXTE'),
    ('MIXTE_TSHIRTS',             'T-shirts',              'MIXTE'),
    ('MIXTE_PANTALONS',           'Pantalons',             'MIXTE'),
    ('MIXTE_JEANS',               'Jeans',                 'MIXTE'),
    ('MIXTE_ASSORTIMENT',         'Assortiment',           'MIXTE'),

    ('TAPISSERIE_SERVIETTES',     'Serviettes',            'TAPISSERIE'),
    ('TAPISSERIE_DRAPS',          'Draps',                 'TAPISSERIE'),
    ('TAPISSERIE_TAPIS',          'Tapis',                 'TAPISSERIE'),
    ('TAPISSERIE_GARNISSAGE',     'Garnissage',            'TAPISSERIE'),
    ('TAPISSERIE_ASSORTIMENT',    'Assortiment',           'TAPISSERIE'),

    ('ACCESSOIRES_CHAUSSURES',    'Chaussures',            'ACCESSOIRES'),
    ('ACCESSOIRES_SACS',          'Sacs',                  'ACCESSOIRES'),
    ('ACCESSOIRES_CEINTURES',     'Ceintures',             'ACCESSOIRES'),
    ('ACCESSOIRES_CASQUETTES',    'Casquettes',            'ACCESSOIRES'),
    ('ACCESSOIRES_FOULARDS',      'Foulards et écharpes',  'ACCESSOIRES'),
    ('ACCESSOIRES_CUIR',          'Cuir',                  'ACCESSOIRES')
) AS n(code, nom, code_parent)
JOIN categories_produits p ON p.code = n.code_parent AND p.parent_id IS NULL
ON CONFLICT DO NOTHING;


-- ------------------------------------------------------------
-- 4. Références fournisseurs (catalogue)
--    Une ligne = un code article d'un fournisseur (ex. SILTEX 2545
--    « Robes femme été ») et son classement Frip'Lux.
--    Classée une fois, la référence est reconnue aux imports suivants.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS references_fournisseurs (
    id                    bigserial     PRIMARY KEY,
    fournisseur_id        bigint        NOT NULL,
    code                  varchar(50)   NOT NULL,
    libelle               varchar(200)  NOT NULL,
    categorie_lot_id      bigint        NOT NULL,
    categorie_produit_id  bigint,
    qualite_id            bigint,
    actif                 boolean       NOT NULL DEFAULT true,
    created_at            timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_references_fournisseur_code UNIQUE (fournisseur_id, code),
    CONSTRAINT chk_references_code_non_vide CHECK (length(trim(code)) > 0),
    CONSTRAINT fk_references_fournisseur FOREIGN KEY (fournisseur_id)
        REFERENCES fournisseurs(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_references_categorie_lot FOREIGN KEY (categorie_lot_id)
        REFERENCES categories_lots(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_references_categorie_produit FOREIGN KEY (categorie_produit_id)
        REFERENCES categories_produits(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_references_qualite FOREIGN KEY (qualite_id)
        REFERENCES qualites(id) ON UPDATE CASCADE ON DELETE RESTRICT
);


-- ------------------------------------------------------------
-- 5. Lots : référence fournisseur, sous-catégorie et qualité
--    Colonnes facultatives : les lots existants ne sont pas touchés.
-- ------------------------------------------------------------
ALTER TABLE lots ADD COLUMN IF NOT EXISTS reference_fournisseur_id bigint;
ALTER TABLE lots ADD COLUMN IF NOT EXISTS categorie_produit_id     bigint;
ALTER TABLE lots ADD COLUMN IF NOT EXISTS qualite_id               bigint;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lots_reference_fournisseur') THEN
        ALTER TABLE lots ADD CONSTRAINT fk_lots_reference_fournisseur FOREIGN KEY (reference_fournisseur_id)
            REFERENCES references_fournisseurs(id) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lots_categorie_produit') THEN
        ALTER TABLE lots ADD CONSTRAINT fk_lots_categorie_produit FOREIGN KEY (categorie_produit_id)
            REFERENCES categories_produits(id) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lots_qualite') THEN
        ALTER TABLE lots ADD CONSTRAINT fk_lots_qualite FOREIGN KEY (qualite_id)
            REFERENCES qualites(id) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_lots_reference_fournisseur ON lots (reference_fournisseur_id);
CREATE INDEX IF NOT EXISTS idx_lots_categorie_produit     ON lots (categorie_produit_id);
CREATE INDEX IF NOT EXISTS idx_lots_qualite               ON lots (qualite_id);
CREATE INDEX IF NOT EXISTS idx_references_fournisseur     ON references_fournisseurs (fournisseur_id);
