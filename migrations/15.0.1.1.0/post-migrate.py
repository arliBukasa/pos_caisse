# Copyright 2025
# Odoo 15.0 migration: adjust FK to SET NULL on pos.caisse.commande.vendeur_id
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # Ensure DB-level FK uses ON DELETE SET NULL for commande -> vendeur
    # Name is typically pos_caisse_commande_vendeur_id_fkey, but detect dynamically
    # Drop vendor FK on commande and recreate with SET NULL.
    # Find FK name dynamically
    cr.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'pos_caisse_commande'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'vendeur_id';
        """
    )
    row = cr.fetchone()
    if row and row[0]:
        fk_name = row[0]
        cr.execute("ALTER TABLE pos_caisse_commande DROP CONSTRAINT %s;" % fk_name)
    # Recreate FK
    cr.execute(
        """
        ALTER TABLE pos_caisse_commande
        ADD CONSTRAINT pos_caisse_commande_vendeur_id_fkey
        FOREIGN KEY (vendeur_id)
        REFERENCES pos_caisse_vendeur(id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED;
        """
    )

    # Adjust FK for commande line -> type_pain to SET NULL to avoid upgrade-time deletes failing
    # Find and drop existing FK on type_pain_id
    cr.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'pos_caisse_commande_line'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'type_pain_id';
        """
    )
    row2 = cr.fetchone()
    if row2 and row2[0]:
        fk2 = row2[0]
        cr.execute("ALTER TABLE pos_caisse_commande_line DROP CONSTRAINT %s;" % fk2)
    cr.execute(
        """
        ALTER TABLE pos_caisse_commande_line
        ADD CONSTRAINT pos_caisse_commande_line_type_pain_id_fkey
        FOREIGN KEY (type_pain_id)
        REFERENCES pos_caisse_type_pain(id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED;
        """
    )
