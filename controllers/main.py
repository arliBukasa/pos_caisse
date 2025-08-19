import logging
from odoo import http
from odoo.http import request, Response

class PosCaisseApi(http.Controller):
    @http.route('/api/pos_caisse/commandes', type='json', auth='user', methods=['GET', 'POST'], csrf=False)
    def create_commande(self, **kwargs):
        """Créer une commande POS avec ses lignes.
        Attendu (JSON):
        {
          "session_id": Optional[int],
          "client_card": Optional[str],
          "client_name": Optional[str],
          "type_paiement": "cash"|"bp",
          "lignes": [{"type_pain_id": int, "quantite": int}],
          "confirm": Optional[bool]
        }
        Retour: { status, commande: {id, name, state, total, mouvement_id?} }
        """
        try:
            params = request.jsonrequest or kwargs or {}
            lignes = params.get('lignes') or []
            type_paiement = params.get('type_paiement') or 'cash'
            confirm = bool(params.get('confirm'))

            if not lignes:
                return {"status": "error", "message": "Aucune ligne fournie."}
            if type_paiement not in ('cash', 'bp'):
                return {"status": "error", "message": "type_paiement invalide (cash|bp)."}

            env = request.env
            uid = request.uid

            # Session
            session_id = params.get('session_id')
            session = None
            if session_id:
                session = env['pos.caisse.session'].sudo().browse(int(session_id))
                if not session or not session.exists():
                    return {"status": "error", "message": "Session introuvable."}
            else:
                session = env['pos.caisse.session'].sudo().search([
                    ('user_id', '=', uid), ('state', '=', 'ouvert')
                ], order='date desc', limit=1)
                if not session:
                    return {"status": "error", "message": "Aucune session ouverte pour l'utilisateur."}

            # Vendeur/Client
            logging.info(f" ======== Création de la commande POS pour les paramettres: {params}")
            client_card = params.get('client_card') or False
            client_name = params.get('client_name') or False
            vendeur_id = False
            if client_card:
                vendeur = env['pos.caisse.vendeur'].sudo().search([('carte_numero', '=', client_card)], limit=1)
                if vendeur:
                    vendeur_id = vendeur.id
                    # si nom non fourni, reprendre celui du vendeur
                    client_name = client_name or vendeur.name

            # recuperation de "idempotency_key" et verifier qu'il n'existe pas d'enregistrement avec cette clé sinon retourner l'enregistrement retrouvé
            idempotency_key = params.get('idempotency_key')
            if idempotency_key:
                existing_commande = env['pos.caisse.commande'].sudo().search([('idempotency_key', '=', idempotency_key)], limit=1)
                if existing_commande:
                    logging.info(f"Commande POS existante trouvée avec idempotency_key {idempotency_key}: {existing_commande.id}")
                    return {"status": "success", "commande": existing_commande}

            # Lignes préparées
            line_vals = []
            for l in lignes:
                tp = l.get('type_pain_id')
                qte = l.get('quantite')
                if not tp or not qte or int(qte) <= 0:
                    return {"status": "error", "message": "Chaque ligne doit avoir type_pain_id et quantite>0."}
                line_vals.append((0, 0, {
                    'type_pain_id': int(tp),
                    'quantite': int(qte),
                }))

            commande_vals = {
                'session_id': session.id,
                'vendeur_id': vendeur_id or False,
                'client_card': client_card,
                'client_name': client_name,
                'type_paiement': type_paiement,
                'line_ids': line_vals,
                'idempotency_key': idempotency_key,
            }

            commande = env['pos.caisse.commande'].sudo().create(commande_vals)

            if confirm:
                commande.sudo().action_confirmer()

            data = {
                'id': commande.id,
                'name': commande.name,
                'state': commande.state,
                'total': commande.total,
                'mouvement_id': commande.mouvement_id.id or None,
            }
            return {"status": "success", "commande": data}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @http.route('/api/pos_caisse/sessions', type='json', auth='user', methods=['GET', 'POST'], csrf=False)
    def get_sessions(self, **kwargs):
        """Lister les sessions (paginées).
        Entrée JSON (optionnel): { state?: 'ouvert'|'ferme', page?: int, limit?: int }
        Retour: { sessions: [...], page, limit, total }
        """
        try:
            params = request.jsonrequest or kwargs or {}
            state = params.get('state')
            page = int(params.get('page') or 1)
            limit = int(params.get('limit') or 50)
            offset = max(0, (page - 1) * limit)

            domain = []
            if state in ('ouvert', 'ferme'):
                domain.append(('state', '=', state))

            env = request.env
            Session = env['pos.caisse.session'].sudo()
            total = Session.search_count(domain)
            sessions = Session.search(domain, order='date desc', offset=offset, limit=limit)

            def _map(s):
                return {
                    'id': s.id,
                    'name': s.name,
                    'date': s.date,
                    'date_cloture': s.date_cloture,
                    'state': s.state,
                    'total_commandes': s.total_commandes,
                    'total_montant': s.total_montant,
                    'total_mouvements': s.total_mouvements,
                    'montant_en_caisse': s.montant_en_caisse,
                    'montant_sortie': s.montant_sortie,
                    'total_bp': s.total_bp,
                }

            return {
                'status': 'success',
                'sessions': [_map(s) for s in sessions],
                'page': page,
                'limit': limit,
                'total': total,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @http.route('/api/pos_caisse/types_pain', type='json', auth='user', methods=['GET','POST'], csrf=False)
    def types_pain(self, **kwargs):
        try:
            params = request.jsonrequest or kwargs or {}
            search = (params.get('search') or '').strip()
            limit = int(params.get('limit') or 200)
            domain = [('active', '=', True)]
            if search:
                domain = ['|', ('name', 'ilike', search), ('prix', '=', search)] + domain
            recs = request.env['pos.caisse.type.pain'].sudo().search(domain, limit=limit)
            data = [{'id': r.id, 'name': r.name, 'prix': r.prix, 'poids': r.poids, 'description': r.description, 'active': r.active} for r in recs]
            return {'status': 'success', 'data': data}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}