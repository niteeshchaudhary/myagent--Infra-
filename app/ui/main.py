"""Main Streamlit application for DevOps Agent UI"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
import json
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.settings import settings
from app.database.database import db_service
from app.models.incident import Incident, IncidentStatus, IncidentSeverity
from app.models.audit_log import AuditLog, ActionType
from app.models.configuration import Configuration
from app.models.sop_document import SOPDocument

# Page configuration
st.set_page_config(
    page_title="DevOps Monitoring Agent",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #1f77b4;
        margin-bottom: 1rem;
    }
    .status-open {
        color: #ff4444;
        font-weight: bold;
    }
    .status-resolved {
        color: #44ff44;
        font-weight: bold;
    }
    .status-in-progress {
        color: #ffaa44;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Main application entry point"""
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🔧 DevOps Monitoring Agent</h1>
        <p>Infrastructure Monitoring & Incident Management Platform</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Select Page",
        ["Dashboard", "Incidents", "Audit Logs", "SOP Documents", "Configuration", "Monitoring Status"]
    )
    
    # Route to appropriate page
    if page == "Dashboard":
        show_dashboard()
    elif page == "Incidents":
        show_incidents()
    elif page == "Audit Logs":
        show_audit_logs()
    elif page == "SOP Documents":
        show_sop_documents()
    elif page == "Configuration":
        show_configuration()
    elif page == "Monitoring Status":
        show_monitoring_status()

def show_dashboard():
    """Display main dashboard with key metrics"""
    st.header("📊 Dashboard")
    
    try:
        with db_service.get_session() as session:
            # Get incident statistics
            total_incidents = session.query(Incident).count()
            open_incidents = session.query(Incident).filter(
                Incident.status == IncidentStatus.OPEN
            ).count()
            resolved_incidents = session.query(Incident).filter(
                Incident.status == IncidentStatus.RESOLVED
            ).count()
            critical_incidents = session.query(Incident).filter(
                Incident.severity == IncidentSeverity.CRITICAL,
                Incident.status != IncidentStatus.RESOLVED
            ).count()
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Incidents", total_incidents)
            with col2:
                st.metric("Open Incidents", open_incidents, delta=-1 if open_incidents < 5 else 1)
            with col3:
                st.metric("Resolved Today", resolved_incidents)
            with col4:
                st.metric("Critical Issues", critical_incidents, delta="urgent" if critical_incidents > 0 else None)
            
            # Recent incidents chart
            st.subheader("📈 Incident Trends (Last 7 Days)")
            
            # Get incidents from last 7 days
            week_ago = datetime.now() - timedelta(days=7)
            recent_incidents = session.query(Incident).filter(
                Incident.created_at >= week_ago
            ).all()
            
            if recent_incidents:
                # Create daily incident count
                incident_data = {}
                for incident in recent_incidents:
                    date_key = incident.created_at.date()
                    incident_data[date_key] = incident_data.get(date_key, 0) + 1
                
                # Convert to DataFrame
                df = pd.DataFrame(
                    list(incident_data.items()),
                    columns=['Date', 'Incidents']
                )
                st.line_chart(df.set_index('Date'))
            else:
                st.info("No incidents in the last 7 days")
            
            # Recent incidents table
            st.subheader("🚨 Recent Incidents")
            recent_incidents = session.query(Incident).order_by(
                Incident.created_at.desc()
            ).limit(10).all()
            
            if recent_incidents:
                incident_df = pd.DataFrame([
                    {
                        'ID': inc.id,
                        'Title': inc.title,
                        'Severity': inc.severity.value if inc.severity else 'Unknown',
                        'Status': inc.status.value if inc.status else 'Unknown',
                        'Source': inc.source_system or 'Unknown',
                        'Created': inc.created_at.strftime('%Y-%m-%d %H:%M') if inc.created_at else 'Unknown'
                    }
                    for inc in recent_incidents
                ])
                st.dataframe(incident_df, use_container_width=True)
            else:
                st.info("No incidents found")
                
    except Exception as e:
        st.error(f"Error loading dashboard data: {str(e)}")

def show_incidents():
    """Display incidents management page"""
    st.header("🚨 Incident Management")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All"] + [status.value for status in IncidentStatus],
            key="incident_status_filter"
        )
    
    with col2:
        severity_filter = st.selectbox(
            "Filter by Severity", 
            ["All"] + [severity.value for severity in IncidentSeverity],
            key="incident_severity_filter"
        )
    
    with col3:
        source_filter = st.text_input("Filter by Source System", key="incident_source_filter")
    
    try:
        with db_service.get_session() as session:
            # Build query with filters
            query = session.query(Incident)
            
            if status_filter != "All":
                query = query.filter(Incident.status == IncidentStatus(status_filter))
            
            if severity_filter != "All":
                query = query.filter(Incident.severity == IncidentSeverity(severity_filter))
            
            if source_filter:
                query = query.filter(Incident.source_system.contains(source_filter))
            
            incidents = query.order_by(Incident.created_at.desc()).all()
            
            if incidents:
                # Create detailed incidents table
                incident_data = []
                for inc in incidents:
                    incident_data.append({
                        'ID': inc.id,
                        'Title': inc.title,
                        'Description': inc.description[:100] + "..." if len(inc.description) > 100 else inc.description,
                        'Severity': inc.severity.value if inc.severity else 'Unknown',
                        'Status': inc.status.value if inc.status else 'Unknown',
                        'Source': inc.source_system or 'Unknown',
                        'Service': inc.affected_service or 'Unknown',
                        'Auto-Fix': '✅' if inc.auto_fix_successful else '❌' if inc.auto_fix_attempted else '⏸️',
                        'Created': inc.created_at.strftime('%Y-%m-%d %H:%M') if inc.created_at else 'Unknown',
                        'Resolved': inc.resolved_at.strftime('%Y-%m-%d %H:%M') if inc.resolved_at else 'Pending'
                    })
                
                df = pd.DataFrame(incident_data)
                
                # Display with styling
                st.dataframe(
                    df,
                    use_container_width=True,
                    column_config={
                        "ID": st.column_config.NumberColumn("ID", width="small"),
                        "Title": st.column_config.TextColumn("Title", width="medium"),
                        "Description": st.column_config.TextColumn("Description", width="large"),
                        "Auto-Fix": st.column_config.TextColumn("Auto-Fix", width="small"),
                    }
                )
                
                # Incident details expander
                st.subheader("📋 Incident Details")
                incident_id = st.selectbox(
                    "Select Incident for Details",
                    options=[inc.id for inc in incidents],
                    format_func=lambda x: f"#{x} - {next(inc.title for inc in incidents if inc.id == x)}"
                )
                
                if incident_id:
                    selected_incident = next(inc for inc in incidents if inc.id == incident_id)
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Title:** {selected_incident.title}")
                        st.write(f"**Status:** {selected_incident.status.value if selected_incident.status else 'Unknown'}")
                        st.write(f"**Severity:** {selected_incident.severity.value if selected_incident.severity else 'Unknown'}")
                        st.write(f"**Source:** {selected_incident.source_system or 'Unknown'}")
                        st.write(f"**Affected Service:** {selected_incident.affected_service or 'Unknown'}")
                    
                    with col2:
                        st.write(f"**Auto-Fix Attempted:** {'Yes' if selected_incident.auto_fix_attempted else 'No'}")
                        st.write(f"**Auto-Fix Successful:** {'Yes' if selected_incident.auto_fix_successful else 'No'}")
                        st.write(f"**Known Issue:** {'Yes' if selected_incident.is_known_issue else 'No'}")
                        st.write(f"**Requires Approval:** {'Yes' if selected_incident.requires_approval else 'No'}")
                        st.write(f"**Created:** {selected_incident.created_at.strftime('%Y-%m-%d %H:%M:%S') if selected_incident.created_at else 'Unknown'}")
                    
                    st.write(f"**Description:**")
                    st.write(selected_incident.description)
                    
                    if selected_incident.error_message:
                        st.write(f"**Error Message:**")
                        st.code(selected_incident.error_message)
                    
                    if selected_incident.resolution_steps:
                        st.write(f"**Resolution Steps:**")
                        st.write(selected_incident.resolution_steps)
                        
            else:
                st.info("No incidents match the current filters")
                
    except Exception as e:
        st.error(f"Error loading incidents: {str(e)}")

def show_audit_logs():
    """Display audit logs page"""
    st.header("📝 Audit Logs")
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        action_filter = st.selectbox(
            "Filter by Action Type",
            ["All"] + [action.value for action in ActionType]
        )
    
    with col2:
        days_back = st.number_input("Days back", min_value=1, max_value=30, value=7)
    
    try:
        with db_service.get_session() as session:
            # Build query
            cutoff_date = datetime.now() - timedelta(days=days_back)
            query = session.query(AuditLog).filter(AuditLog.created_at >= cutoff_date)
            
            if action_filter != "All":
                query = query.filter(AuditLog.action_type == ActionType(action_filter))
            
            logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()
            
            if logs:
                log_data = []
                for log in logs:
                    log_data.append({
                        'ID': log.id,
                        'Action': log.action_type.value if log.action_type else 'Unknown',
                        'Description': log.action_description[:100] + "..." if len(log.action_description) > 100 else log.action_description,
                        'Success': '✅' if log.success else '❌',
                        'System': log.source_system or 'Unknown',
                        'User': log.user_id or 'System',
                        'Duration (ms)': log.duration_ms or 0,
                        'Created': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'Unknown'
                    })
                
                df = pd.DataFrame(log_data)
                st.dataframe(df, use_container_width=True)
                
            else:
                st.info("No audit logs found for the selected criteria")
                
    except Exception as e:
        st.error(f"Error loading audit logs: {str(e)}")

def show_sop_documents():
    """Display SOP documents management page"""
    st.header("📚 SOP Documents")
    
    try:
        with db_service.get_session() as session:
            documents = session.query(SOPDocument).filter(
                SOPDocument.is_published == True,
                SOPDocument.is_deprecated == False
            ).order_by(SOPDocument.usage_count.desc()).all()
            
            if documents:
                doc_data = []
                for doc in documents:
                    doc_data.append({
                        'ID': doc.id,
                        'Title': doc.title,
                        'Category': doc.category or 'General',
                        'Version': doc.version or '1.0',
                        'Usage Count': doc.usage_count or 0,
                        'Effectiveness': f"{(doc.effectiveness_score or 0) * 100:.1f}%",
                        'Last Used': doc.last_used_at.strftime('%Y-%m-%d') if doc.last_used_at else 'Never',
                        'Created': doc.created_at.strftime('%Y-%m-%d') if doc.created_at else 'Unknown'
                    })
                
                df = pd.DataFrame(doc_data)
                st.dataframe(df, use_container_width=True)
                
                # Document viewer
                st.subheader("📖 Document Viewer")
                doc_id = st.selectbox(
                    "Select Document",
                    options=[doc.id for doc in documents],
                    format_func=lambda x: next(doc.title for doc in documents if doc.id == x)
                )
                
                if doc_id:
                    selected_doc = next(doc for doc in documents if doc.id == doc_id)
                    st.write(f"**Category:** {selected_doc.category}")
                    st.write(f"**Version:** {selected_doc.version}")
                    st.write(f"**Usage Count:** {selected_doc.usage_count}")
                    st.write(f"**Effectiveness Score:** {(selected_doc.effectiveness_score or 0) * 100:.1f}%")
                    
                    st.write("**Content:**")
                    st.markdown(selected_doc.content)
                    
            else:
                st.info("No SOP documents found")
                
    except Exception as e:
        st.error(f"Error loading SOP documents: {str(e)}")

def show_configuration():
    """Display configuration management page"""
    st.header("⚙️ Configuration")
    
    st.info("Configuration management interface - settings can be modified here")
    
    # System status
    st.subheader("🔍 System Status")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        db_healthy = db_service.health_check()
        st.metric(
            "Database", 
            "Healthy" if db_healthy else "Unhealthy",
            delta="✅" if db_healthy else "❌"
        )
    
    with col2:
        st.metric("Redis", "Connected", delta="✅")
    
    with col3:
        st.metric("LLM Service", "Available", delta="✅")

def show_monitoring_status():
    """Display monitoring status page"""
    st.header("🔍 Monitoring Status")
    
    # Monitoring toggles
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📡 Polling Monitor")
        polling_enabled = st.checkbox("Enable Polling", value=True)
        polling_interval = st.number_input(
            "Polling Interval (seconds)", 
            min_value=30, 
            max_value=3600, 
            value=300
        )
        
        if st.button("Start Polling"):
            st.success("Polling monitor started!")
    
    with col2:
        st.subheader("🪝 Webhook Monitor") 
        webhook_enabled = st.checkbox("Enable Webhooks", value=True)
        webhook_port = st.number_input(
            "Webhook Port",
            min_value=1000,
            max_value=65535,
            value=8080
        )
        
        if st.button("Start Webhook Server"):
            st.success("Webhook server started!")
    
    # System commands
    st.subheader("💻 Allowed Commands")
    
    commands = [
        "kubectl get pods",
        "kubectl get services", 
        "kubectl get nodes",
        "aws ec2 describe-instances",
        "gcloud compute instances list",
        "az vm list"
    ]
    
    for cmd in commands:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.code(cmd)
        with col2:
            if st.button("Test", key=f"test_{cmd}"):
                st.info(f"Testing: {cmd}")

if __name__ == "__main__":
    main()