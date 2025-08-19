{
    'name': 'POS Caisse - Sumni v2',
    'version': '15.0.1.0.0',
    'summary': 'Gestion de caisse, commandes, sessions, mouvements de caisse avec API REST pour application mobile',
    'description': '''
        Module de gestion de caisse pour POS Sumni v2:
        - Sessions de caisse avec dashboard
        - Commandes avec paiement Cash et BP (fin de mois)
        - Mouvements de caisse automatiques
        - Interface pour caissiers
        - API REST pour application mobile Android
        - Rapports de vente avec impression
    ''',
    'author': 'Sumni POS Team',
    'website': 'https://github.com/sumni-pos',
    'category': 'Point of Sale',
    'depends': [
        'base',
        'web',
    ],
    'data': [
        'security/pos_caisse_security.xml',
        'security/ir.model.access.csv',
        'data/pos_caisse_data.xml',
        'views/pos_caisse_views.xml',
        'views/pos_caisse_menu.xml',
        'reports/rapport_vente_template.xml',  # Template de rapport
    ],
    'demo': [
        # 'demo/demo_data.xml',  # Données de démonstration
    ],
    'qweb': [
        # 'static/src/xml/pos_templates.xml',  # Templates JS si nécessaire
    ],
    'external_dependencies': {
        'python': ['requests'],  # Pour l'API REST
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
