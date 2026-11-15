This script is designed to backfill my eBay store's data into a local database to be used with the Tavus integration. I need to make a new schema to support the Tavus usecase. The schema should be:

id - UUID
listing_url - TEXT
scryfall_url - TEXT
colour_identity - TEXT
name - TEXT
price - DECIMAL

The way we will need to backfill this database is use the eBay APIs to fetch iteratively every page of listings and convert them into the schema data above. The ebay listings will not have scryfall_url or colour_identity, this will need to be fetched after getting the name of the card from the eBay title. You can correlate the name of the eBay card to the row in prod_data/prod.sqlite3 card_phash table, this table has the scryfall_id that can be used to get more information required for this table, such as the colour_identity.

Create a script that:

1) fetches each page of the ebay listings from my production account on eBay (I will run the script from Arcanum so I will have the credentials setup there)
2) extracts the name of the listing and any relevant information (colour identity might be on the listing data)
3) using the phash_data table to fill in any other information required (this has the scryfall_id : name columns so you can find the name of the card, then do a scryfall lookup if needed)
4) write the data to inventory.sqlite3

This script only needs to be run once, and the data accuracy doesn't need to be too high. I just need a good amount of data in the table, ideally >90% of what I have on eBay. For reference, I currently have around 1000 unique listings. 

Create the script and I will run it in Arcanum.