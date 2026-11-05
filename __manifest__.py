# -*- coding: utf-8 -*-
{
    'name': 'Transport',
    'version': '19.0.31.0.0',
    'summary': 'Départs, billets QR, embarquement et contrats entreprise',
    'description': """
Exploitation d'un réseau hybride (navettes entreprise et lignes interurbaines).

Le siège se compte par tronçon. La confirmation émet un billet QR.
La checklist critique et les habilitations du chauffeur bloquent le départ.
    """,
    'category': 'Operations/Transport',
    'author': 'Chakib',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'fleet',
        'hr',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/checklist.xml',
        'data/mail_template.xml',
        'data/algeria_network.xml',
        'data/device_token.xml',
        'reports/ticket_report.xml',
        'reports/statement_report.xml',
        'views/stop_views.xml',
        'views/line_views.xml',
        'views/vehicle_views.xml',
        'views/schedule_views.xml',
        'views/departure_views.xml',
        'views/booking_views.xml',
        'views/operation_views.xml',
        'wizard/generate_departures_views.xml',
        'wizard/operations_views.xml',
        'wizard/board_scan_views.xml',
        'views/booking_templates.xml',
        'views/boarding_templates.xml',
        'views/tracking_templates.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
