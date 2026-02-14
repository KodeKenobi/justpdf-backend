
from database import db
from models import AnalyticsEvent
from app import app
from datetime import datetime

with app.app_context():
    ad_clicks = AnalyticsEvent.query.filter_by(event_name='ad_click').all()
    print(f"Total Ad Clicks: {len(ad_clicks)}")
    
    simulated_clicks = [c for c in ad_clicks if c.properties.get('simulated') == True]
    print(f"Simulated Clicks: {len(simulated_clicks)}")
    
    for click in ad_clicks[-5:]:
        print(f"ID: {click.id}, Time: {click.timestamp}, Simulated: {click.properties.get('simulated')}, Page: {click.page_url}")
