from odoo import models, fields, api
from datetime import datetime

class PosVendeur(models.Model):
    _name = 'pos.caisse.vendeur'
    _description = 'Vendeur/Client'
    _order = 'name'

    name = fields.Char('Nom du vendeur', required=True, help="Nom complet du vendeur")
    carte_numero = fields.Char('Numéro de carte', required=True, help="Numéro de carte unique du vendeur")
    telephone = fields.Char('Téléphone')
    adresse = fields.Text('Adresse')
    active = fields.Boolean('Actif', default=True)
    pourcentage_commission = fields.Float('Commission (%)', default=25.0, help="Pourcentage de commission sur les ventes")
    # commandes
    commande_ids = fields.One2many('pos.caisse.commande', 'vendeur_id', string="Commandes")
    # Statistiques calculées
    total_commandes = fields.Integer('Nombre de commandes', compute='_compute_stats', store=True)
    total_ventes = fields.Float('Total des ventes', compute='_compute_stats', store=True)
    commission_totale = fields.Float('Commission totale', compute='_compute_stats', store=True)

    _sql_constraints = [
        ('carte_numero_unique', 'unique(carte_numero)', 'Le numéro de carte doit être unique !'),
        ('pourcentage_valid', 'check(pourcentage_commission >= 0 AND pourcentage_commission <= 100)', 'Le pourcentage doit être entre 0 et 100 !'),
    ]

    @api.depends('carte_numero')
    def _compute_stats(self):
        """Calculer les statistiques de vente pour chaque vendeur"""
        for vendeur in self:
            # Chercher les commandes liées à ce vendeur
            commandes = self.env['pos.caisse.commande'].search(['|', ('client_card', '=', vendeur.carte_numero), ('vendeur_id', '=', vendeur.id)])
            vendeur.total_commandes = len(commandes)
            vendeur.total_ventes = sum(commandes.mapped('total'))
            vendeur.commission_totale = vendeur.total_ventes * (vendeur.pourcentage_commission / 100)

    def name_get(self):
        """Affichage personnalisé dans les listes déroulantes"""
        result = []
        for vendeur in self:
            name = f"{vendeur.carte_numero} - {vendeur.name}"
            result.append((vendeur.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Recherche par numéro de carte ou nom"""
        if args is None:
            args = []
        
        if name:
            # Rechercher par numéro de carte ou nom
            domain = ['|', ('carte_numero', 'ilike', name), ('name', 'ilike', name)]
            vendeurs = self.search(domain + args, limit=limit)
            return vendeurs.name_get()
        
        return super().name_search(name, args, operator, limit)

class TypePain(models.Model):
    _name = 'pos.caisse.type.pain'
    _description = 'Type de pain'
    _order = 'name'

    name = fields.Char('Nom du pain', required=True, help="Ex: Pain complet, Pain blanc, Baguette...")
    prix = fields.Float('Prix unitaire', required=True, help="Prix en FC")
    poids = fields.Float('Poids', required=True, help="Poids en grammes")
    description = fields.Text('Description')
    active = fields.Boolean('Actif', default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Le nom du type de pain doit être unique !'),
        ('prix_positive', 'check(prix > 0)', 'Le prix doit être supérieur à zéro !'),
        ('poids_positive', 'check(poids > 0)', 'Le poids doit être supérieur à zéro !'),
    ]

    def name_get(self):
        """Affichage personnalisé dans les listes déroulantes"""
        result = []
        for pain in self:
            name = f"{pain.name} ({pain.prix} FC - {pain.poids}g)"
            result.append((pain.id, name))
        return result

    def unlink(self):
        """Archive (active=False) au lieu de supprimer si référencé par des lignes de commande.

        Cela évite les échecs d'upgrade lorsque Odoo tente de supprimer des enregistrements
        fournis par des données XML qui sont désormais absentes, tout en préservant l'historique.
        """
        Line = self.env['pos.caisse.commande.line'].sudo()
        to_delete = self.browse()
        for rec in self:
            if Line.search_count([('type_pain_id', '=', rec.id)]):
                # Archiver au lieu de supprimer
                rec.active = False
            else:
                to_delete |= rec
        if to_delete:
            return super(TypePain, to_delete).unlink()
        return True

class PosSession(models.Model):
    _name = 'pos.caisse.session'
    _description = 'Session de caisse'
    _order = 'date desc'

    name = fields.Char('Nom de la session', required=True, default=lambda self: self._get_default_session_name())
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    date_cloture = fields.Datetime('Date de clôture')
    user_id = fields.Many2one('res.users', string='Caissier', required=True, default=lambda self: self.env.user)
    state = fields.Selection([
        ('ouvert', 'Ouverte'),
        ('ferme', 'Clôturée')
    ], default='ouvert', string='État')
    commande_ids = fields.One2many('pos.caisse.commande', 'session_id', string='Commandes')
    mouvement_ids = fields.One2many('pos.caisse.mouvement', 'session_id', string='Mouvements de caisse')
    
    # Champs calculés pour le dashboard
    total_commandes = fields.Integer('Nombre de commandes', compute='_compute_dashboard_data', store=True)
    total_montant = fields.Float('Montant total des commandes', compute='_compute_dashboard_data', store=True)
    total_mouvements = fields.Integer('Nombre de mouvements', compute='_compute_dashboard_data', store=True)
    montant_en_caisse = fields.Float('Montant en caisse', compute='_compute_montant_caisse', store=True)
    montant_sortie = fields.Float('Montant des sorties', compute='_compute_montant_caisse', store=True)
    total_bp = fields.Float('Total des commandes BP', compute='_compute_dashboard_data', store=True)
    
    def _get_default_session_name(self):
        """Génère automatiquement le nom de session"""
        today = datetime.now().strftime('%Y-%m-%d')
        return f"Session-{today}"

    @api.depends('commande_ids', 'commande_ids.total', 'commande_ids.type_paiement')
    def _compute_dashboard_data(self):
        for session in self:
            session.total_commandes = len(session.commande_ids)
            session.total_montant = sum(session.commande_ids.mapped('total'))
            # Total des commandes BP (payées à la fin du mois)
            session.total_bp = sum(session.commande_ids.filtered(lambda c: c.type_paiement == 'bp').mapped('total'))

    @api.depends('mouvement_ids', 'mouvement_ids.montant', 'mouvement_ids.type')
    def _compute_montant_caisse(self):
        for session in self:
            entrees = sum(session.mouvement_ids.filtered(lambda m: m.type == 'entree').mapped('montant'))
            sorties = sum(session.mouvement_ids.filtered(lambda m: m.type == 'sortie').mapped('montant'))
            session.montant_en_caisse = entrees - sorties
            session.montant_sortie = sorties
            session.total_mouvements = len(session.mouvement_ids)

    def action_open_session(self):
        """Ouvrir une session fermée"""
        self.ensure_one()
        self.state = 'ouvert'
        self.date_cloture = False
        return True

    def action_close_session(self):
        """Fermer une session ouverte"""
        self.ensure_one()
        self.state = 'ferme'
        self.date_cloture = fields.Datetime.now()
        return True

    def action_print_rapport_vente(self):
        """Imprimer le rapport de vente de fin de session"""
        self.ensure_one()
        return {
            'type': 'ir.actions.report',
            'report_name': 'pos_caisse.rapport_vente_session',
            'report_type': 'qweb-pdf',
            'data': {'session_id': self.id},
            'context': self.env.context,
        }

class PosCommande(models.Model):
    _name = 'pos.caisse.commande'
    _description = 'Commande de caisse'
    _order = 'date desc'

    name = fields.Char('Numéro commande', default=lambda self: self._get_sequence(), copy=False)
    session_id = fields.Many2one('pos.caisse.session', string='Session', required=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    
    # Champs vendeur avec autocomplétion
    vendeur_id = fields.Many2one(
        'pos.caisse.vendeur',
        string='Vendeur',
        help="Sélectionner le vendeur",
        ondelete='set null',  # Don't block deletion of vendeur; keep historical orders with card/name
    )
    client_card = fields.Char('Numéro de carte client', help="Identifiant principal du client/vendeur")
    client_name = fields.Char('Nom du client', help="Nom complet du client/vendeur")
    
    type_paiement = fields.Selection([
        ('cash', 'Cash'),
        ('bp', 'BP (Fin de mois)')
    ], default='cash', string='Type de paiement', required=True)
    # Vente cash (VC): si coché, la livraison doit inclure +25% de commission
    is_vc = fields.Boolean('Vente cash (VC)', default=False, help="Si activé, le total cible de livraison inclut +25% de commission")
    line_ids = fields.One2many('pos.caisse.commande.line', 'commande_id', string='Lignes de commande')
    total = fields.Float('Total général', compute='_compute_total', store=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirme', 'Confirmée'),
        ('en_attente_livraison', 'En attente de livraison'),
        ('livre', 'Livrée'),
        ('annule', 'Annulée')
    ], default='draft', string='État')
    paiement_state = fields.Selection([
        ('non_payee', 'Non payée'),
        ('payee', 'Payée')
    ], default='non_payee', string='État du paiement')

    mouvement_id = fields.Many2one('pos.caisse.mouvement', string='Mouvement de caisse associé')
    idempotency_key = fields.Char('Clé d\'idempotence', help="Clé unique pour éviter les doublons de commande")

    def _get_sequence(self):
        """Génère le numéro de séquence pour la commande"""
        return self.env['ir.sequence'].next_by_code('pos.caisse.commande') or '/'

    @api.depends('line_ids.sous_total')
    def _compute_total(self):
        for commande in self:
            commande.total = sum(line.sous_total for line in commande.line_ids)

    @api.onchange('vendeur_id')
    def _onchange_vendeur_id(self):
        """Remplir automatiquement les champs client quand on sélectionne un vendeur"""
        if self.vendeur_id:
            self.client_card = self.vendeur_id.carte_numero
            self.client_name = self.vendeur_id.name
            self._onchange_client_card()

    @api.onchange('client_card')
    def _onchange_client_card(self):
        """Autocomplétion du nom quand on saisit le numéro de carte"""
        if self.client_card:
            # Chercher le vendeur correspondant
            vendeur = self.env['pos.caisse.vendeur'].search([
                ('carte_numero', '=', self.client_card)
            ], limit=1)
            
            if vendeur:
                self.client_name = vendeur.name
                self.vendeur_id = vendeur.id
            else:
                # Si le vendeur n'existe pas, vider le nom et proposer de créer
                self.client_name = ''
                self.vendeur_id = False

    @api.model
    def create(self, vals):
        """Enforce vendor linkage and auto-create vendor by card if missing.

        - If a client card is provided and no vendeur_id, try to link to existing vendor.
        - If not found, create a new pos.caisse.vendeur with the provided card and name, then link it.
        """
        card = vals.get('client_card')
        if card and not vals.get('vendeur_id'):
            Vendeur = self.env['pos.caisse.vendeur'].sudo()
            v = Vendeur.search([('carte_numero', '=', card)], limit=1)
            if not v:
                # Create vendor automatically if it doesn't exist
                name = vals.get('client_name') or f"Carte {card}"
                try:
                    v = Vendeur.create({
                        'name': name,
                        'carte_numero': card,
                        'active': True,
                    })
                except Exception:
                    # Handle rare race: if created concurrently, fetch it
                    v = Vendeur.search([('carte_numero', '=', card)], limit=1)
            if v:
                vals['vendeur_id'] = v.id
                if not vals.get('client_name'):
                    vals['client_name'] = v.name
        return super().create(vals)

    def write(self, vals):
        """Auto-link vendor on client_card change and update mouvement on total change"""
        # If the client card is updated and no vendeur_id provided, link/create vendor
        if vals.get('client_card') and not vals.get('vendeur_id'):
            card = vals.get('client_card')
            if card:
                Vendeur = self.env['pos.caisse.vendeur'].sudo()
                v = Vendeur.search([('carte_numero', '=', card)], limit=1)
                if not v:
                    name = vals.get('client_name') or f"Carte {card}"
                    try:
                        v = Vendeur.create({'name': name, 'carte_numero': card, 'active': True})
                    except Exception:
                        v = Vendeur.search([('carte_numero', '=', card)], limit=1)
                if v:
                    vals['vendeur_id'] = v.id
                    if not vals.get('client_name'):
                        vals['client_name'] = v.name

        result = super().write(vals)
        for commande in self:
            if commande.mouvement_id and 'total' in vals:
                # Mettre à jour le montant du mouvement existant
                commande.mouvement_id.montant = commande.total
                commande.mouvement_id.motif = f'Commande {commande.name} - Client: {commande.client_name} (Mise à jour)'
        return result

    def action_confirmer(self):
        """Confirmer la commande et créer le mouvement de caisse"""
        for commande in self:
            if commande.state == 'draft':
                commande.state = 'confirme'
                
                # Créer le mouvement de caisse pour les commandes Cash
                if commande.type_paiement == 'cash' and not commande.mouvement_id:
                    mouvement = self.env['pos.caisse.mouvement'].create({
                        'session_id': commande.session_id.id,
                        'type': 'entree',
                        'montant': commande.total,
                        'motif': f'Commande {commande.name} - Client: {commande.client_name}',
                        'commande_id': commande.id,
                    })
                    commande.mouvement_id = mouvement.id
                
                # Passer automatiquement en attente de livraison
                commande.state = 'en_attente_livraison'
        
        return True

    def action_annuler(self):
        """Annuler la commande et supprimer le mouvement de caisse associé"""
        for commande in self:
            if commande.mouvement_id:
                commande.mouvement_id.unlink()
            commande.state = 'annule'
        return True

class PosCommandeLine(models.Model):
    _name = 'pos.caisse.commande.line'
    _description = 'Ligne de commande'

    commande_id = fields.Many2one('pos.caisse.commande', string='Commande', required=True, ondelete='cascade')
    type_pain_id = fields.Many2one('pos.caisse.type.pain', string='Type de pain', required=True, ondelete='cascade')
    quantite = fields.Integer('Quantité', required=True, default=1)
    prix_unitaire = fields.Float('Prix unitaire', related='type_pain_id.prix', store=True, readonly=False)
    poids_unitaire = fields.Float('Poids unitaire (g)', related='type_pain_id.poids', readonly=True)
    poids_total = fields.Float('Poids total (g)', compute='_compute_poids_total', store=True)
    sous_total = fields.Float('Sous-total', compute='_compute_sous_total', store=True)  


    @api.depends('quantite', 'poids_unitaire')
    def _compute_poids_total(self):
        for line in self:
            line.poids_total = line.quantite * line.poids_unitaire

    @api.depends('quantite', 'prix_unitaire')
    def _compute_sous_total(self):
        for line in self:
            line.sous_total = line.quantite * line.prix_unitaire

    @api.onchange('type_pain_id')
    def _onchange_type_pain(self):
        """Mettre à jour le prix unitaire quand le type de pain change"""
        if self.type_pain_id:
            self.prix_unitaire = self.type_pain_id.prix

    def name_get(self):
        """Affichage personnalisé dans les listes"""
        result = []
        for line in self:
            if line.type_pain_id:
                name = f"{line.type_pain_id.name} x{line.quantite} ({line.sous_total} FC)"
            else:
                name = f"Ligne {line.id}"
            result.append((line.id, name))
        return result

class PosMouvement(models.Model):
    _name = 'pos.caisse.mouvement'
    _description = 'Mouvement de caisse'
    _order = 'date desc'

    session_id = fields.Many2one('pos.caisse.session', string='Session', required=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    type = fields.Selection([
        ('entree', 'Entrée (Commande)'),
        ('sortie', 'Sortie de caisse')
    ], required=True, string='Type de mouvement')
    montant = fields.Float('Montant', required=True)
    motif = fields.Char('Motif', required=True, help="Raison du mouvement")
    commande_id = fields.Many2one('pos.caisse.commande', string='Commande liée')
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, required=True)
    
    # Champs pour lier aux paies (ajoutés dynamiquement depuis le contexte)
    paie_vendeur_id = fields.Many2one('pos.paie.vendeur', string='Paie Vendeur liée')
    paie_wizard_id = fields.Many2one('pos.paie.wizard', string='Paie Wizard liée')

    @api.constrains('montant')
    def _check_montant_positif(self):
        """Vérifier que le montant est positif"""
        for mouvement in self:
            if mouvement.montant <= 0:
                raise ValueError("Le montant doit être supérieur à zéro.")

    @api.constrains('session_id', 'type')
    def _check_session_ouverte(self):
        """Vérifier que la session est ouverte pour créer des mouvements"""
        for mouvement in self:
            if mouvement.session_id.state == 'ferme':
                raise ValueError("Impossible de créer un mouvement sur une session fermée.")

    @api.model
    def create(self, vals):
        """Validation lors de la création et confirmation automatique des paies"""
        # Valider que le motif est renseigné pour les sorties
        if vals.get('type') == 'sortie' and not vals.get('motif'):
            raise ValueError("Le motif est obligatoire pour les sorties de caisse.")
        
        # Récupérer les IDs de paie depuis le contexte si présents
        ctx = self.env.context or {}
        paie_vendeur_id = ctx.get('default_paie_vendeur_id')
        paie_wizard_id = ctx.get('default_paie_wizard_id')
        
        if paie_vendeur_id:
            vals['paie_vendeur_id'] = paie_vendeur_id
        if paie_wizard_id:
            vals['paie_wizard_id'] = paie_wizard_id
        
        mouvement = super().create(vals)
        
        # Confirmer automatiquement les paies associées après création du mouvement
        if mouvement.type == 'sortie':
            if mouvement.paie_vendeur_id:
                try:
                    mouvement.paie_vendeur_id.action_confirmer_paie()
                except Exception as e:
                    import logging
                    logging.warning("Erreur lors de la confirmation de la paie vendeur %s: %s", mouvement.paie_vendeur_id.id, str(e))
            
            if mouvement.paie_wizard_id:
                try:
                    mouvement.paie_wizard_id.action_confirmer_paie()
                except Exception as e:
                    import logging
                    logging.warning("Erreur lors de la confirmation de la paie wizard %s: %s", mouvement.paie_wizard_id.id, str(e))
        
        return mouvement
