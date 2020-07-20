# -*- coding: utf-8 -*-
# Copyright (C) 2019 Sergio Corato
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Product cost evaluation",
    "version": "12.0.1.0.0",
    "depends": [
        'stock',
        'purchase',
    ],
    "author": "Sergio Corato, Alex Comba, Gianmarco Conte"
              "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/stock-logistics-warehouse",
    "category": "Warehouse Management",
    "installable": True,
    "license": "AGPL-3",
    "data": [
        'security/ir.model.access.csv',
        'views/product_cost_evaluation_history.xml',
        'views/stock_inventory_evaluation.xml', #DA
    ]
}
