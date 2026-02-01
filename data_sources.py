print('=== SOURCES ALTERNATIVES POUR DONNÉES RÉELLES ===')
print()

sources = [
    {
        'nom': 'Alpha Vantage',
        'url': 'https://www.alphavantage.co/documentation/',
        'description': 'API gratuite avec données d\'options',
        'type': 'API (clé requise)'
    },
    {
        'nom': 'IEX Cloud',
        'url': 'https://iexcloud.io/docs/api/',
        'description': 'API professionnelle pour données boursières',
        'type': 'API (clé requise)'
    },
    {
        'nom': 'Polygon.io',
        'url': 'https://polygon.io/docs/options',
        'description': 'API spécialisée options et dérivés',
        'type': 'API (clé requise)'
    },
    {
        'nom': 'CBOE API',
        'url': 'https://www.cboe.com/us/options/market_statistics/',
        'description': 'API officielle Chicago Board Options Exchange',
        'type': 'API gratuite'
    },
    {
        'nom': 'Téléchargement manuel',
        'url': 'https://www.cboe.com/delayed_quotes/spx/quote_table',
        'description': 'Tableur Excel avec données SPX options',
        'type': 'Fichier Excel'
    }
]

for i, source in enumerate(sources, 1):
    print(f'{i}. {source["nom"]}')
    print(f'   URL: {source["url"]}')
    print(f'   Description: {source["description"]}')
    print(f'   Type: {source["type"]}')
    print()