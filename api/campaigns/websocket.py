"""
WebSocket endpoints for live campaign monitoring
"""
from flask import Blueprint
from flask_sock import Sock
import asyncio
import json

# This will be registered with the main app's Sock instance
def register_websocket_routes(sock):
    """Register WebSocket routes with the Sock instance"""
    
    @sock.route('/ws/campaign/<int:campaign_id>/monitor/<int:company_id>')
    def campaign_monitor(ws, campaign_id, company_id):
        """WebSocket endpoint for live campaign monitoring"""
        print(f"WebSocket connected for campaign {campaign_id}, company {company_id}")
        
        try:
            # Get campaign and company data
            from models import Campaign, Company, db
            
            company = Company.query.filter_by(
                id=company_id,
                campaign_id=campaign_id
            ).first()
            
            if not company:
                ws.send(json.dumps({
                    'type': 'error',
                    'data': {'message': 'Company not found'}
                }))
                return
            
            campaign = Campaign.query.get(campaign_id)
            if not campaign:
                ws.send(json.dumps({
                    'type': 'error',
                    'data': {'message': 'Campaign not found'}
                }))
                return
            
            # Send initial status
            ws.send(json.dumps({
                'type': 'connected',
                'data': {
                    'campaign_id': campaign_id,
                    'company_id': company_id,
                    'company_name': company.company_name,
                    'website_url': company.website_url
                }
            }))
            
            # Prepare company data
            company_data = {
                'company_name': company.company_name,
                'website_url': company.website_url,
                'contact_email': company.contact_email,
                'phone': company.phone
            }
            
            # Run the scraper with live streaming
            from services.live_scraper import LiveScraper
            scraper = LiveScraper(ws, company_data, campaign.message_template, campaign_id, company_id)
            
            # Run async scraper in sync context
            import nest_asyncio
            nest_asyncio.apply()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run scraper async
            result = loop.run_until_complete(scraper.scrape_and_submit())
            loop.close()
            
            # If cancelled, don't send completion
            if result.get('cancelled'):
                print(f"[CANCEL] Process was cancelled, not sending completion message")
                company.status = 'cancelled'
                db.session.commit()
                return
            
            # Send final result
            ws.send(json.dumps({
                'type': 'completed',
                'data': result
            }))
            
            # Update company status in database
            if result.get('success'):
                company.status = 'completed'
            else:
                company.status = 'failed'
                company.error_message = result.get('error')
            
            # Save screenshot URL if available
            if result.get('screenshot_url'):
                company.screenshot_url = result.get('screenshot_url')
            
            db.session.commit()
            
        except Exception as e:
            print(f"[WebSocket Error] {e}")
            import traceback
            traceback.print_exc()
            
            # Send detailed error to frontend for debugging
            error_message = str(e)
            error_type = type(e).__name__
            
            try:
                ws.send(json.dumps({
                    'type': 'error',
                    'data': {
                        'message': f'{error_type}: {error_message}',
                        'error_type': error_type,
                        'details': error_message
                    }
                }))
            except:
                pass
        
        print(f"WebSocket disconnected for campaign {campaign_id}, company {company_id}")
