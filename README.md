# pos_caisse – Documentation technique

Module Odoo 15 pour la gestion de caisse, commandes, sessions, mouvements de caisse, et API REST pour l’application mobile.

## Modèles et champs clés

### pos.caisse.vendeur (Vendeur/Client)
- name (Char) – Nom du vendeur
- carte_numero (Char, unique) – Identifiant principal
- telephone (Char), adresse (Text), active (Boolean)
- pourcentage_commission (Float, %)
- commande_ids (One2many → pos.caisse.commande)
- total_commandes (Integer, compute)
- total_ventes (Float, compute)
- commission_totale (Float, compute)

Calculs (_compute_stats):
- Recherche les commandes liées par carte (client_card = carte_numero) ou lien direct (vendeur_id = id)
- total_commandes = nombre de commandes
- total_ventes = somme des champs total
- commission_totale = total_ventes × (pourcentage_commission/100)

Ergonomie:
- name_get: « carte_numero – name »
- name_search: recherche par carte_numero ou name

### pos.caisse.commande (Commande)
- session_id (Many2one pos.caisse.session)
- date (Datetime)
- vendeur_id (Many2one pos.caisse.vendeur) – NOUVEAU: sélection directe du vendeur
- client_card (Char) – Numéro de carte du client/vendeur
- client_name (Char) – Nom client
- type_paiement (Selection: cash|bp)
- line_ids (One2many pos.caisse.commande.line)
- total (Float, compute)
- state (Selection)
- mouvement_id (Many2one pos.caisse.mouvement)
- idempotency_key (Char)

Comportements liés au vendeur:
- onchange(vendeur_id): remplit client_card et client_name depuis le vendeur et déclenche l’onchange client_card
- onchange(client_card): associe automatiquement vendeur_id si une carte existe; sinon vide vendeur_id/client_name
- create(): si client_card est renseigné et vendeur_id absent, lie automatiquement le vendeur correspondant

## Interface utilisateur

- Formulaire Commande: champ vendeur_id ajouté dans le groupe d’en-tête
- Fiche Vendeur: onglet « Commandes » affichant les commandes liées (name, date, type_paiement, total, state) avec somme sur la colonne total
- Fiche Vendeur: bloc « Statistiques » affichant total_commandes, total_ventes, commission_totale

## API POS Caisse (extraits)

### Créer une commande
Endpoint: POST /api/pos_caisse/commandes (type=json)

Entrée (JSON minimal):
{
	"session_id": 123,                  // optionnel; sinon session ouverte de l’utilisateur
	"client_card": "V001",            // lie automatiquement vendeur_id si carte existante
	"client_name": "Nom Client",      // optionnel; repris du vendeur si absent
	"type_paiement": "cash",          // "cash" ou "bp"
	"lignes": [ { "type_pain_id": 1, "quantite": 2 } ],
	"confirm": true,                    // optionnel; confirme et crée le mouvement si cash
	"idempotency_key": "<uuid>"       // optionnel; évite les doublons
}

Sortie (succès):
{
	"status": "success",
	"commande": { "id": 10, "name": "CMD00010", "state": "en_attente_livraison", "total": 444000, "mouvement_id": 55 }
}

Notes:
- vendeur_id est résolu côté serveur à partir de client_card si fourni; lier vendeur_id directement est aussi supporté via create()
- Si confirm=true et type_paiement=cash: un mouvement d’entrée de caisse est créé
- Si idempotency_key correspond à une commande existante: la commande existante est renvoyée

### Sessions (liste/ouverture/fermeture)
Endpoint: /api/pos_caisse/sessions (type=json)
- list: { state?: "ouvert"|"ferme", page?: int, limit?: int }
- open: { state: "open" }
- close: { state: "close", session_id?: int }

## Installation
Copiez ce dossier dans le répertoire des modules Odoo (addons), mettez à jour la liste des applications, puis installez/mettez à jour le module via l’interface Odoo.
