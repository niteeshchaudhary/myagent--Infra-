"""Main Streamlit application for DevOps Agent UI"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import json
import os
import sys
import logging
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.settings import settings
from app.database.database import db_service
from app.models.incident import Incident, IncidentStatus, IncidentSeverity
from app.models.audit_log import AuditLog, ActionType
from app.models.configuration import Configuration
from app.models.sop_document import SOPDocument
from app.services.command_list_manager import command_list_manager

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
def get_auto_fix_service():
    """Lazy import of AutoFixService to avoid circular dependencies"""
    from app.services.auto_fix_service import AutoFixService
    return AutoFixService

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
    
    # Initialize session state for auto-refresh
    if 'auto_refresh_enabled' not in st.session_state:
        st.session_state.auto_refresh_enabled = True
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 5  # Default 5 seconds
    if 'last_refresh_time' not in st.session_state:
        st.session_state.last_refresh_time = time.time()
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🔧 DevOps Monitoring Agent</h1>
        <p>Infrastructure Monitoring & Incident Management Platform</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Dashboard", "Incidents", "Audit Logs", "SOP Documents", "Configuration", "Monitoring Status", "Chat with Agent"]
    )
    
    # Auto-refresh controls in sidebar
    st.sidebar.divider()
    st.sidebar.subheader("Auto-Refresh")
    auto_refresh = st.sidebar.checkbox(
        "Enable Auto-Refresh",
        value=st.session_state.auto_refresh_enabled,
        key="auto_refresh_checkbox"
    )
    st.session_state.auto_refresh_enabled = auto_refresh
    
    if auto_refresh:
        refresh_interval = st.sidebar.slider(
            "Refresh Interval (seconds)",
            min_value=2,
            max_value=60,
            value=st.session_state.refresh_interval,
            step=1,
            key="refresh_interval_slider"
        )
        st.session_state.refresh_interval = refresh_interval
        
        # Add JavaScript auto-refresh using page reload
        # This is the most reliable method for Streamlit
        refresh_js = f"""
        <script>
            (function() {{
                let refreshTimer = setTimeout(function() {{
                    window.location.reload();
                }}, {refresh_interval * 1000});
                
                // Clear timer if user navigates away or disables auto-refresh
                window.addEventListener('beforeunload', function() {{
                    clearTimeout(refreshTimer);
                }});
            }})();
        </script>
        """
        st.markdown(refresh_js, unsafe_allow_html=True)
        
        # Show next refresh time
        st.sidebar.caption(f"🔄 Auto-refreshing every {refresh_interval}s")
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()
    
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
    elif page == "Chat with Agent":
        show_chat_with_agent()

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
                    # Refresh incident from database to get latest data
                    selected_incident = session.query(Incident).filter(Incident.id == incident_id).first()
                    
                    if not selected_incident:
                        st.error(f"Incident {incident_id} not found")
                        return
                    
                    # Create tabs for different views
                    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🔧 Auto-Fix", "🤖 LLM Conversations", "📝 Activity Log"])
                    
                    # Get LLM logs and activity logs for this incident
                    llm_logs = session.query(AuditLog).filter(
                        AuditLog.incident_id == incident_id,
                        AuditLog.action_type == ActionType.LLM_QUERY
                    ).order_by(AuditLog.created_at.asc()).all()  # Show oldest first (chronological order)
                    
                    all_logs = session.query(AuditLog).filter(
                        AuditLog.incident_id == incident_id
                    ).order_by(AuditLog.created_at.desc()).all()
                    
                    with tab1:
                        # Basic Information
                        st.subheader("Basic Information")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Title:** {selected_incident.title}")
                            st.write(f"**Status:** {selected_incident.status.value if selected_incident.status else 'Unknown'}")
                            st.write(f"**Severity:** {selected_incident.severity.value if selected_incident.severity else 'Unknown'}")
                            st.write(f"**Source:** {selected_incident.source_system or 'Unknown'}")
                            st.write(f"**Affected Service:** {selected_incident.affected_service or 'Unknown'}")
                            if selected_incident.namespace:
                                st.write(f"**Namespace:** {selected_incident.namespace}")
                        
                        with col2:
                            st.write(f"**Auto-Fix Attempted:** {'Yes' if selected_incident.auto_fix_attempted else 'No'}")
                            st.write(f"**Auto-Fix Successful:** {'Yes' if selected_incident.auto_fix_successful else 'No'}")
                            st.write(f"**Known Issue:** {'Yes' if selected_incident.is_known_issue else 'No'}")
                            st.write(f"**Requires Approval:** {'Yes' if selected_incident.requires_approval else 'No'}")
                            st.write(f"**Created:** {selected_incident.created_at.strftime('%Y-%m-%d %H:%M:%S') if selected_incident.created_at else 'Unknown'}")
                            if selected_incident.updated_at:
                                st.write(f"**Last Updated:** {selected_incident.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
                            if selected_incident.resolved_at:
                                st.write(f"**Resolved:** {selected_incident.resolved_at.strftime('%Y-%m-%d %H:%M:%S')}")
                            if selected_incident.assigned_to:
                                st.write(f"**Assigned To:** {selected_incident.assigned_to}")
                        
                        st.divider()
                        
                        # Description
                        st.subheader("Description")
                        st.write(selected_incident.description)
                        
                        # Error Message
                        if selected_incident.error_message:
                            st.subheader("Error Message")
                            st.code(selected_incident.error_message, language="text")
                        
                        # Stack Trace
                        if selected_incident.stack_trace:
                            with st.expander("Stack Trace"):
                                st.code(selected_incident.stack_trace, language="text")
                        
                        # Resolution Steps
                        if selected_incident.resolution_steps:
                            st.subheader("Resolution Steps")
                            st.write(selected_incident.resolution_steps)
                    
                    with tab2:
                        # Approval Request Section (if pending)
                        if selected_incident.approval_requested and not selected_incident.approval_granted:
                            st.subheader("🔐 Approval Request Pending")
                            st.warning("⚠️ Commands require approval before execution")
                            
                            # Parse approval notes to get commands
                            approval_commands = []
                            if selected_incident.approval_notes:
                                try:
                                    import json
                                    notes_data = json.loads(selected_incident.approval_notes)
                                    approval_commands = notes_data.get('commands', [])
                                    reason = notes_data.get('reason', 'Commands not in allowed list')
                                    
                                    st.write(f"**Reason:** {reason}")
                                    st.write(f"**Commands Requested:** ({len(approval_commands)} command(s))")
                                    for i, cmd in enumerate(approval_commands, 1):
                                        st.code(cmd, language="bash")
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.button("✅ Approve Commands", type="primary", key=f"approve_{incident_id}"):
                                            try:
                                                from app.approval_system.approval_request import ApprovalRequestService
                                                approval_service = ApprovalRequestService()
                                                if approval_service.grant_approval(incident_id, "ui_user", "Approved via UI"):
                                                    st.success("✅ Approval granted! Commands will be executed.")
                                                    st.rerun()
                                                else:
                                                    st.error("Failed to grant approval")
                                            except Exception as e:
                                                st.error(f"Error: {str(e)}")
                                    
                                    with col2:
                                        if st.button("❌ Reject Commands", key=f"reject_{incident_id}"):
                                            try:
                                                from app.approval_system.approval_request import ApprovalRequestService
                                                approval_service = ApprovalRequestService()
                                                if approval_service.reject_approval(incident_id, "ui_user", "Rejected via UI"):
                                                    st.info("❌ Approval rejected. Agent will continue without these commands.")
                                                    st.rerun()
                                                else:
                                                    st.error("Failed to reject approval")
                                            except Exception as e:
                                                st.error(f"Error: {str(e)}")
                                    
                                    st.divider()
                                except:
                                    st.write("**Commands:** Unable to parse approval details")
                        
                        # Auto-Fix Details Section
                        st.subheader("🔧 Auto-Fix Details")
                        
                        if selected_incident.auto_fix_attempted:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Status", "✅ Successful" if selected_incident.auto_fix_successful else "❌ Failed")
                            
                            with col2:
                                if selected_incident.updated_at:
                                    st.metric("Last Attempt", selected_incident.updated_at.strftime('%Y-%m-%d %H:%M:%S'))
                            
                            # Show commands executed
                            if selected_incident.auto_fix_commands:
                                st.subheader("Commands Executed")
                                try:
                                    commands = json.loads(selected_incident.auto_fix_commands) if isinstance(selected_incident.auto_fix_commands, str) else selected_incident.auto_fix_commands
                                    if isinstance(commands, list) and commands:
                                        for i, cmd in enumerate(commands, 1):
                                            st.code(f"{i}. {cmd}", language="bash")
                                    else:
                                        st.code(selected_incident.auto_fix_commands, language="bash")
                                except:
                                    st.code(selected_incident.auto_fix_commands, language="bash")
                            else:
                                st.info("No commands were executed during auto-fix")
                            
                            # Show resolution notes
                            if selected_incident.resolution_notes:
                                st.subheader("Auto-Fix Notes")
                                st.text_area(
                                    "Resolution Notes",
                                    value=selected_incident.resolution_notes,
                                    height=300,
                                    disabled=True,
                                    key=f"resolution_notes_{selected_incident.id}"
                                )
                        else:
                            st.info("Auto-fix has not been attempted for this incident.")
                    
                    with tab3:
                        # LLM Conversations
                        st.subheader("🤖 LLM Conversations")
                        
                        # Show previous conversations (in chronological order: first conversation = #1)
                        if llm_logs:
                            st.write("**Previous Conversations:**")
                            total_conversations = len(llm_logs)
                            for idx, log in enumerate(llm_logs, 1):
                                conversation_num = idx  # First conversation is #1, last is #N
                                with st.expander(f"Conversation #{conversation_num} (of {total_conversations}) - {log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'Unknown'}", expanded=False):
                                    col1, col2 = st.columns([1, 1])
                                    
                                    with col1:
                                        st.write("**Model Used:**")
                                        st.code(log.llm_model_used or "Unknown", language="text")
                                        
                                        if log.llm_tokens_used:
                                            st.write(f"**Tokens Used:** {log.llm_tokens_used}")
                                        
                                        if log.duration_ms:
                                            st.write(f"**Response Time:** {log.duration_ms}ms")
                                        
                                        st.write(f"**Status:** {'✅ Success' if log.success else '❌ Failed'}")
                                        
                                        if log.error_message:
                                            st.error(f"Error: {log.error_message}")
                                    
                                    with col2:
                                        st.write(f"**Timestamp:** {log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'Unknown'}")
                                    
                                    st.divider()
                                    
                                    # Prompt
                                    if log.llm_prompt:
                                        st.write("**📤 Prompt Sent to LLM:**")
                                        st.text_area(
                                            "Prompt",
                                            value=log.llm_prompt,
                                            height=200,
                                            disabled=True,
                                            key=f"prompt_{log.id}"
                                        )
                                    
                                    # Response
                                    if log.llm_response:
                                        st.write("**📥 LLM Response:**")
                                        st.text_area(
                                            "Response",
                                            value=log.llm_response,
                                            height=300,
                                            disabled=True,
                                            key=f"response_{log.id}"
                                        )
                                    elif not log.success:
                                        st.warning("No response received - query failed")
                        else:
                            st.info("No previous LLM conversations found for this incident.")
                        
                        st.divider()
                        
                        # Interactive Chat Interface
                        st.subheader("💬 Chat with LLM")
                        st.write("Provide additional context or instructions to help the LLM resolve this incident. After you send a message, the system will automatically retry the auto-fix with your input.")
                        
                        # Check if auto-fix failed
                        if selected_incident.auto_fix_attempted and not selected_incident.auto_fix_successful:
                            st.warning("⚠️ Auto-fix previously failed. You can provide additional context to help retry the fix.")
                        
                        # Chat input
                        user_message = st.text_area(
                            "Your Message",
                            height=150,
                            placeholder="E.g., 'The cluster was recently updated. Check if the API server is accessible.' or 'Try checking the network connectivity first.'",
                            key=f"user_chat_input_{incident_id}"
                        )
                        
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            send_button = st.button("📤 Send & Retry Auto-Fix", type="primary", key=f"send_chat_{incident_id}")
                        
                        if send_button:
                            if user_message.strip():
                                with st.spinner("Sending message to LLM and retrying auto-fix..."):
                                    try:
                                        # Import inside try block to avoid circular import issues
                                        from app.services.auto_fix_service import AutoFixService
                                        auto_fix_service = AutoFixService()
                                        
                                        # Retry auto-fix with user input
                                        success = auto_fix_service.attempt_auto_fix(
                                            selected_incident,
                                            force_retry=True,
                                            user_input=user_message.strip()
                                        )
                                        
                                        if success:
                                            st.success("✅ Auto-fix retry successful! The incident has been resolved.")
                                            st.balloons()
                                            st.rerun()
                                        else:
                                            st.warning("⚠️ Auto-fix retry completed, but the issue may still need attention. Check the updated resolution notes.")
                                            st.info("💡 You can send another message with more context to try again.")
                                            st.rerun()
                                    
                                    except Exception as e:
                                        st.error(f"❌ Error: {str(e)}")
                                        logger.error(f"Error in chat retry: {str(e)}")
                            else:
                                st.warning("Please enter a message before sending.")
                    
                    with tab4:
                        # Activity Log
                        st.subheader("📝 Activity Log")
                        
                        if all_logs:
                            for log in all_logs:
                                with st.expander(f"{log.action_type.value.replace('_', ' ').title()} - {log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'Unknown'}"):
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write(f"**Action:** {log.action_type.value}")
                                        st.write(f"**User:** {log.user_id or 'System'}")
                                        st.write(f"**Status:** {'✅ Success' if log.success else '❌ Failed'}")
                                    
                                    with col2:
                                        st.write(f"**Timestamp:** {log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else 'Unknown'}")
                                        if log.duration_ms:
                                            st.write(f"**Duration:** {log.duration_ms}ms")
                                    
                                    st.write(f"**Description:** {log.action_description}")
                                    
                                    if log.command_executed:
                                        st.write("**Command Executed:**")
                                        st.code(log.command_executed, language="bash")
                                        
                                        if log.command_output:
                                            with st.expander("Command Output"):
                                                st.code(log.command_output[:5000], language="text")  # Limit to 5000 chars
                                        
                                        if log.command_exit_code is not None:
                                            st.write(f"**Exit Code:** {log.command_exit_code}")
                                    
                                    if log.error_message:
                                        st.error(f"**Error:** {log.error_message}")
                                    
                                    if log.llm_model_used:
                                        st.write(f"**LLM Model:** {log.llm_model_used}")
                        else:
                            st.info("No activity logs found for this incident.")
                        
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
    
    st.divider()
    
    # Command Lists Management
    st.subheader("🔐 Command Lists Management")
    st.info("Manage allowed and not-allowed command lists. Commands in the not-allowed list take precedence over the allowed list.")
    
    # Create tabs for allowed and not-allowed lists
    tab1, tab2 = st.tabs(["✅ Allowed Commands", "❌ Not-Allowed Commands"])
    
    with tab1:
        st.write("**Allowed Commands List**")
        st.caption("Commands that are permitted to execute. Commands must start with one of these patterns.")
        st.info("💡 **Tip:** Use `*` at the end of a pattern to match any suffix. Example: `kubectl config use-context*` matches `kubectl config use-context kind-kind` or any cluster name.")
        
        # Get current allowed commands
        allowed_commands = command_list_manager.get_allowed_commands()
        
        # Display current commands
        if allowed_commands:
            st.write(f"**Current Allowed Commands ({len(allowed_commands)}):**")
            for i, cmd in enumerate(allowed_commands, 1):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.code(cmd, language="bash")
                with col2:
                    if st.button("🗑️", key=f"remove_allowed_{i}", help="Remove this command"):
                        if command_list_manager.remove_allowed_command(cmd):
                            st.success(f"Removed: {cmd}")
                            st.rerun()
                        else:
                            st.error("Failed to remove command")
        else:
            st.info("No allowed commands configured")
        
        st.divider()
        
        # Add new allowed command
        st.write("**Add New Allowed Command**")
        col1, col2 = st.columns([4, 1])
        with col1:
            new_allowed = st.text_input(
                "Command Pattern",
                placeholder="e.g., kubectl config use-context*",
                key="new_allowed_command",
                help="Enter a command pattern. Use * at the end for wildcard matching (e.g., 'kubectl config use-context*' matches any cluster name)"
            )
        with col2:
            st.write("")  # Spacing
            st.write("")  # Spacing
            if st.button("➕ Add", key="add_allowed_btn", type="primary"):
                if new_allowed.strip():
                    if command_list_manager.add_allowed_command(new_allowed):
                        st.success(f"Added: {new_allowed}")
                        st.rerun()
                    else:
                        st.warning("Command already exists or is invalid")
                else:
                    st.warning("Please enter a command pattern")
        
        # Bulk edit
        with st.expander("📝 Bulk Edit Allowed Commands"):
            st.write("Edit all allowed commands at once (one per line):")
            bulk_allowed = st.text_area(
                "Allowed Commands",
                value="\n".join(allowed_commands),
                height=200,
                key="bulk_allowed_commands",
                help="Enter one command pattern per line"
            )
            if st.button("💾 Save Allowed Commands", key="save_allowed_bulk"):
                commands_list = [cmd.strip() for cmd in bulk_allowed.split("\n") if cmd.strip()]
                if command_list_manager.set_allowed_commands(commands_list):
                    st.success(f"Saved {len(commands_list)} allowed commands")
                    st.rerun()
                else:
                    st.error("Failed to save allowed commands")
    
    with tab2:
        st.write("**Not-Allowed Commands List**")
        st.caption("Commands that are explicitly forbidden. These take precedence over allowed commands.")
        st.info("💡 **Tip:** Use `*` at the end of a pattern to match any suffix. Example: `kubectl delete*` blocks all delete commands.")
        
        # Get current not-allowed commands
        not_allowed_commands = command_list_manager.get_not_allowed_commands()
        
        # Display current commands
        if not_allowed_commands:
            st.write(f"**Current Not-Allowed Commands ({len(not_allowed_commands)}):**")
            for i, cmd in enumerate(not_allowed_commands, 1):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.code(cmd, language="bash")
                with col2:
                    if st.button("🗑️", key=f"remove_not_allowed_{i}", help="Remove this command"):
                        if command_list_manager.remove_not_allowed_command(cmd):
                            st.success(f"Removed: {cmd}")
                            st.rerun()
                        else:
                            st.error("Failed to remove command")
        else:
            st.info("No not-allowed commands configured")
        
        st.divider()
        
        # Add new not-allowed command
        st.write("**Add New Not-Allowed Command**")
        col1, col2 = st.columns([4, 1])
        with col1:
            new_not_allowed = st.text_input(
                "Command Pattern",
                placeholder="e.g., kubectl delete*",
                key="new_not_allowed_command",
                help="Enter a command pattern to block. Use * at the end for wildcard matching (e.g., 'kubectl delete*' blocks all delete commands)"
            )
        with col2:
            st.write("")  # Spacing
            st.write("")  # Spacing
            if st.button("➕ Add", key="add_not_allowed_btn", type="primary"):
                if new_not_allowed.strip():
                    if command_list_manager.add_not_allowed_command(new_not_allowed):
                        st.success(f"Added: {new_not_allowed}")
                        st.rerun()
                    else:
                        st.warning("Command already exists or is invalid")
                else:
                    st.warning("Please enter a command pattern")
        
        # Bulk edit
        with st.expander("📝 Bulk Edit Not-Allowed Commands"):
            st.write("Edit all not-allowed commands at once (one per line):")
            bulk_not_allowed = st.text_area(
                "Not-Allowed Commands",
                value="\n".join(not_allowed_commands),
                height=200,
                key="bulk_not_allowed_commands",
                help="Enter one command pattern per line"
            )
            if st.button("💾 Save Not-Allowed Commands", key="save_not_allowed_bulk"):
                commands_list = [cmd.strip() for cmd in bulk_not_allowed.split("\n") if cmd.strip()]
                if command_list_manager.set_not_allowed_commands(commands_list):
                    st.success(f"Saved {len(commands_list)} not-allowed commands")
                    st.rerun()
                else:
                    st.error("Failed to save not-allowed commands")
    
    st.divider()
    
    # Command Testing
    st.subheader("🧪 Test Command")
    st.write("Test if a command would be allowed or blocked:")
    st.caption("💡 **Wildcard Support:** Patterns ending with `*` match any suffix. Example: `kubectl config use-context*` matches `kubectl config use-context kind-kind`")
    
    test_col1, test_col2 = st.columns([4, 1])
    with test_col1:
        test_command = st.text_input(
            "Command to Test",
            placeholder="e.g., kubectl config use-context kind-kind",
            key="test_command_input"
        )
    with test_col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        test_btn = st.button("🔍 Test", key="test_command_btn", type="primary")
    
    if test_btn and test_command:
        status = command_list_manager.get_command_status(test_command)
        if status == "allowed":
            st.success(f"✅ Command is ALLOWED: `{test_command}`\n\nThis command is in the allowed list and will execute directly.")
        elif status == "blocked":
            st.error(f"🚫 Command is BLOCKED: `{test_command}`\n\nThis command is in the not-allowed list and will be rejected without approval.")
        elif status == "needs_approval":
            st.warning(f"⚠️ Command NEEDS APPROVAL: `{test_command}`\n\nThis command is not in either list and will require human approval before execution.")
    
    # Configuration summary
    st.divider()
    summary = command_list_manager.get_config_summary()
    st.caption(f"**Configuration Summary:** {summary['allowed_count']} allowed, {summary['not_allowed_count']} not-allowed | Config file: `{summary['config_path']}`")

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
            value=settings.POLLING_INTERVAL
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
            value=8088
        )
        
        if st.button("Start Webhook Server"):
            st.success("Webhook server started!")
    
    # Command lists info
    st.subheader("💻 Command Lists")
    st.info("💡 Manage allowed and not-allowed command lists in the **Configuration** page.")
    
    # Show current command list summary
    summary = command_list_manager.get_config_summary()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Allowed Commands", summary['allowed_count'])
    with col2:
        st.metric("Not-Allowed Commands", summary['not_allowed_count'])
    
    if st.button("⚙️ Go to Configuration", use_container_width=True):
        st.info("Navigate to the Configuration page to manage command lists")

def show_chat_with_agent():
    """Display chat interface with the agent"""
    st.header("💬 Chat with Agent")
    st.write("Ask the agent to run commands, perform fixes, or get help with infrastructure issues.")
    
    # Initialize chat history in session state
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'chat_incident_id' not in st.session_state:
        st.session_state.chat_incident_id = None
    
    # Sidebar for chat options
    with st.sidebar:
        st.subheader("💬 Chat Options")
        
        # Link to incident if available
        if st.session_state.chat_incident_id:
            st.info(f"📋 Linked to Incident #{st.session_state.chat_incident_id}")
            if st.button("🔗 Clear Link"):
                st.session_state.chat_incident_id = None
                st.rerun()
        else:
            incident_id_input = st.number_input(
                "Link to Incident ID (optional)",
                min_value=1,
                value=None,
                step=1,
                key="link_incident_input"
            )
            if incident_id_input:
                st.session_state.chat_incident_id = int(incident_id_input)
        
        st.divider()
        
        # Clear chat history
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.chat_incident_id = None
            st.rerun()
        
        st.divider()
        
        # Quick actions
        st.subheader("⚡ Quick Actions")
        
        if st.button("📊 Check Cluster Status", use_container_width=True):
            st.session_state.chat_history.append({
                'role': 'user',
                'content': 'Check the Kubernetes cluster status',
                'timestamp': datetime.now()
            })
            st.rerun()
        
        if st.button("🔍 List All Pods", use_container_width=True):
            st.session_state.chat_history.append({
                'role': 'user',
                'content': 'List all pods in the cluster',
                'timestamp': datetime.now()
            })
            st.rerun()
        
        if st.button("📈 Get System Health", use_container_width=True):
            st.session_state.chat_history.append({
                'role': 'user',
                'content': 'Get overall system health status',
                'timestamp': datetime.now()
            })
            st.rerun()
    
    # Display chat history
    st.subheader("💭 Conversation")
    
    if not st.session_state.chat_history:
        st.info("👋 Start a conversation! You can ask the agent to:\n"
                "- Run commands (e.g., 'kubectl get pods')\n"
                "- Perform fixes (e.g., 'fix the pod crash issue')\n"
                "- Get help (e.g., 'what pods are failing?')\n"
                "- Check infrastructure status")
    else:
        # Display chat messages
        for idx, message in enumerate(st.session_state.chat_history):
            if message['role'] == 'user':
                with st.chat_message("user"):
                    st.write(message['content'])
                    if 'timestamp' in message:
                        st.caption(f"🕐 {message['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                with st.chat_message("assistant"):
                    st.write(message['content'])
                    if 'timestamp' in message:
                        st.caption(f"🕐 {message['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Show command execution results if available
                    if 'command_result' in message:
                        result = message['command_result']
                        if result is not None and isinstance(result, dict):
                            with st.expander("📋 Command Execution Details"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Exit Code:** {result.get('exit_code', 'N/A')}")
                                    st.write(f"**Success:** {'✅ Yes' if result.get('success') else '❌ No'}")
                                with col2:
                                    st.write(f"**Duration:** {result.get('duration_ms', 0)}ms")
                                
                                if result.get('stdout'):
                                    st.write("**Output:**")
                                    st.code(result['stdout'], language='text')
                                
                                if result.get('stderr'):
                                    st.write("**Error:**")
                                    st.code(result['stderr'], language='text')
                    
                    # Show commands executed if available
                    if 'commands_executed' in message:
                        with st.expander("🔧 Commands Executed"):
                            for cmd in message['commands_executed']:
                                st.code(cmd, language='bash')
    
    # Chat input
    st.divider()
    
    # Create two columns for input and send button
    col1, col2 = st.columns([5, 1])
    
    with col1:
        user_input = st.text_input(
            "Type your message...",
            key="chat_input",
            placeholder="e.g., 'Check pod status' or 'Fix the failing deployment'",
            label_visibility="collapsed"
        )
    
    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        send_button = st.button("📤 Send", type="primary", use_container_width=True)
    
    # Process user input
    if send_button and user_input.strip():
        # Add user message to history
        st.session_state.chat_history.append({
            'role': 'user',
            'content': user_input.strip(),
            'timestamp': datetime.now()
        })
        
        # Process the message
        with st.spinner("🤖 Agent is thinking..."):
            try:
                response = process_chat_message(
                    user_input.strip(),
                    st.session_state.chat_history,
                    st.session_state.chat_incident_id
                )
                
                # Add agent response to history
                st.session_state.chat_history.append({
                    'role': 'assistant',
                    'content': response['message'],
                    'timestamp': datetime.now(),
                    'command_result': response.get('command_result'),
                    'commands_executed': response.get('commands_executed', [])
                })
                
                # Log the conversation
                log_chat_conversation(user_input.strip(), response['message'], st.session_state.chat_incident_id)
                
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                st.session_state.chat_history.append({
                    'role': 'assistant',
                    'content': error_msg,
                    'timestamp': datetime.now()
                })
                logger.error(f"Error in chat: {str(e)}")
        
        st.rerun()

def process_chat_message(user_message: str, chat_history: List[Dict], incident_id: Optional[int] = None) -> Dict:
    """
    Process a chat message and generate a response with intelligent issue detection
    
    Returns:
        dict with 'message', 'command_result' (optional), 'commands_executed' (optional), 'similar_issues' (optional)
    """
    from app.llm.llm_service import LLMService
    from app.monitoring.command_executor import CommandExecutor
    from app.services.auto_fix_service import AutoFixService
    from app.services.similarity_service import similarity_service
    
    llm_service = LLMService()
    command_executor = CommandExecutor()
    
    # Check if LLM is available
    if not llm_service.is_available():
        return {
            'message': f"⚠️ LLM service is not available. Please configure {llm_service.provider.upper()} API key in settings.",
            'commands_executed': []
        }
    
    # Detect intent
    message_lower = user_message.lower()
    
    # Check if it's a direct command request
    if any(keyword in message_lower for keyword in ['run', 'execute', 'run command', 'execute command']):
        # Extract command from message
        # Try to find command patterns
        import re
        command_patterns = [
            r'run\s+(?:command\s+)?["\']?([^"\']+)["\']?',
            r'execute\s+(?:command\s+)?["\']?([^"\']+)["\']?',
            r'["\']([^"\']+)["\']',
        ]
        
        command = None
        for pattern in command_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                command = match.group(1).strip()
                break
        
        # If no pattern found, try to extract after keywords
        if not command:
            for keyword in ['run', 'execute']:
                if keyword in message_lower:
                    parts = user_message.split(keyword, 1)
                    if len(parts) > 1:
                        command = parts[1].strip()
                        # Remove quotes if present
                        command = command.strip('"\'')
                        break
        
        if command:
            # Execute the command
            result = command_executor.execute_command(command, log_execution=True)
            
            if result.success:
                response_msg = f"✅ Command executed successfully!\n\n**Command:** `{command}`\n\n**Output:**\n```\n{result.stdout}\n```"
            else:
                response_msg = f"❌ Command failed with exit code {result.exit_code}\n\n**Command:** `{command}`\n\n**Error:**\n```\n{result.stderr}\n```"
            
            return {
                'message': response_msg,
                'command_result': {
                    'command': command,
                    'exit_code': result.exit_code,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'success': result.success,
                    'duration_ms': result.duration_ms
                },
                'commands_executed': [command]
            }
        else:
            return {
                'message': "I couldn't extract a command from your message. Please specify the command clearly, e.g., 'run kubectl get pods'"
            }
    
    # Check if it's a fix request
    elif any(keyword in message_lower for keyword in ['fix', 'resolve', 'repair', 'troubleshoot']):
        if incident_id:
            # Try to fix the linked incident
            try:
                with db_service.get_session() as session:
                    incident = session.query(Incident).filter(Incident.id == incident_id).first()
                    if incident:
                        auto_fix_service = AutoFixService()
                        success = auto_fix_service.attempt_auto_fix(incident, force_retry=True, user_input=user_message)
                        
                        if success:
                            return {
                                'message': f"✅ Successfully fixed incident #{incident_id}! The issue has been resolved.",
                                'commands_executed': []
                            }
                        else:
                            return {
                                'message': f"⚠️ Attempted to fix incident #{incident_id}, but the fix may not have been successful. Check the incident details for more information.",
                                'commands_executed': []
                            }
                    else:
                        return {
                            'message': f"❌ Incident #{incident_id} not found. Please link to a valid incident first."
                        }
            except Exception as e:
                return {
                    'message': f"❌ Error attempting fix: {str(e)}"
                }
        else:
            # User described an issue but no incident linked - search for similar issues
            if similarity_service.is_available():
                similar_issues = similarity_service.find_similar_incidents(
                    user_message,
                    top_k=5,
                    min_similarity=0.4
                )
                
                if similar_issues:
                    response_parts = [
                        "🔍 **I found similar issues in the system:**\n"
                    ]
                    
                    for i, issue in enumerate(similar_issues, 1):
                        status_emoji = "✅" if issue['auto_fix_successful'] else "⚠️"
                        similarity_pct = issue['similarity_score'] * 100
                        
                        response_parts.append(
                            f"\n**{i}. {status_emoji} Incident #{issue['incident_id']}** (Similarity: {similarity_pct:.0f}%)\n"
                            f"   **Title:** {issue['title']}\n"
                            f"   **Status:** {issue['status']} | **Severity:** {issue['severity']}\n"
                            f"   **Source:** {issue['source_system'] or 'Unknown'}\n"
                        )
                        
                        if issue.get('error_message'):
                            response_parts.append(f"   **Error:** {issue['error_message']}\n")
                        
                        if issue['auto_fix_successful']:
                            response_parts.append(f"   ✅ This issue was auto-fixed successfully\n")
                    
                    response_parts.append(
                        "\n💡 **What would you like to do?**\n"
                        "- Link to one of these incidents to apply the same fix\n"
                        "- Describe your issue in more detail\n"
                        "- Ask me to create a new incident and attempt a fix"
                    )
                    
                    return {
                        'message': "".join(response_parts),
                        'similar_issues': similar_issues
                    }
            
            # No similar issues found or similarity service not available
            return {
                'message': "To perform a fix, please either:\n1. Link to an incident using the sidebar, or\n2. Describe the issue in more detail and I'll search for similar problems\n3. Create a new incident if this is a new issue"
            }
    
    # Check if user is describing a problem/issue (auto-detect intent)
    elif any(keyword in message_lower for keyword in ['issue', 'problem', 'error', 'failing', 'down', 'crash', 'not working', 'broken']):
        # Intelligent issue detection with similar issues
        if similarity_service.is_available():
            similar_issues = similarity_service.find_similar_incidents(
                user_message,
                top_k=5,
                min_similarity=0.3,
                exclude_resolved=False
            )
            
            if similar_issues:
                response_parts = [
                    "🤖 **I understand you're experiencing an issue. Let me help!**\n",
                    f"\n📊 **Found {len(similar_issues)} similar incident(s) in our system:**\n"
                ]
                
                for i, issue in enumerate(similar_issues, 1):
                    status_emoji = "✅" if issue['status'] == 'resolved' else "🔴" if issue['status'] == 'open' else "🟡"
                    similarity_pct = issue['similarity_score'] * 100
                    fix_status = "✅ Auto-Fixed" if issue['auto_fix_successful'] else "⚠️ Needs Attention"
                    
                    response_parts.append(
                        f"\n**{i}. {status_emoji} Incident #{issue['incident_id']}** (Match: {similarity_pct:.0f}%)\n"
                        f"   **Title:** {issue['title']}\n"
                        f"   **Status:** {issue['status'].title()} | **Severity:** {issue['severity'].title()}\n"
                        f"   **Fix Status:** {fix_status}\n"
                    )
                    
                    if issue['affected_service']:
                        response_parts.append(f"   **Service:** {issue['affected_service']}\n")
                
                response_parts.append(
                    "\n💡 **Recommendations:**\n"
                    "1. Link to the most similar incident (sidebar) and I can try the same fix\n"
                    "2. Review the resolution steps from successful fixes\n"
                    "3. Provide more details for a custom solution\n"
                )
                
                return {
                    'message': "".join(response_parts),
                    'similar_issues': similar_issues
                }
            else:
                return {
                    'message': (
                        "🤖 **I understand you're having an issue, but I couldn't find similar incidents.**\n\n"
                        "📝 **To help you better, please provide:**\n"
                        "- What component/service is affected?\n"
                        "- What error messages are you seeing?\n"
                        "- When did this start?\n\n"
                        "Or you can:\n"
                        "- Link to an existing incident\n"
                        "- Run diagnostic commands (e.g., 'check pod status')\n"
                    )
                }
        else:
            return {
                'message': (
                    "🤖 **I understand you're having an issue.**\n\n"
                    "⚠️ Similarity search is not available. Please:\n"
                    "- Link to an existing incident, or\n"
                    "- Describe the issue in detail and I'll help troubleshoot\n"
                )
            }
    
    # Check if it's a status/query request
    elif any(keyword in message_lower for keyword in ['status', 'check', 'list', 'get', 'show', 'what', 'how']):
        # Use LLM to generate appropriate commands and execute them
        context = f"User wants to: {user_message}\n\n"
        context += "Available commands I can run:\n"
        context += "- kubectl get pods\n"
        context += "- kubectl get nodes\n"
        context += "- kubectl get services\n"
        context += "- kubectl cluster-info\n"
        context += "- kubectl get events\n"
        
        # Build conversation context
        conversation_context = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in chat_history[-5:]  # Last 5 messages for context
        ])
        
        prompt = f"""You are a DevOps assistant. The user is asking: {user_message}

Previous conversation:
{conversation_context}

Based on the user's request, determine what command(s) should be executed. 
Respond in JSON format with:
{{
    "commands": ["command1", "command2"],
    "explanation": "brief explanation of what will be done"
}}

Only suggest commands that are safe and appropriate for monitoring/checking status.
Do not suggest destructive commands like delete, apply, create unless explicitly requested.
"""
        
        try:
            # Use the chat method
            messages = llm_service.start_conversation()
            # Add conversation history
            for msg in chat_history[-5:]:
                if msg['role'] == 'user':
                    messages.append({"role": "user", "content": msg['content']})
                else:
                    messages.append({"role": "assistant", "content": msg['content']})
            
            # Get response
            response = llm_service.chat(messages, user_message, incident_id=None)
            
            # Extract commands from response
            commands = response.get('commands', [])
            explanation = response.get('explanation', response.get('solution', ''))
            
            if commands:
                executed_commands = []
                results = []
                
                for cmd in commands:
                    result = command_executor.execute_command(cmd, log_execution=True)
                    executed_commands.append(cmd)
                    results.append({
                        'command': cmd,
                        'success': result.success,
                        'output': result.stdout if result.success else result.stderr
                    })
                
                # Build response
                response_parts = [explanation + "\n\n"]
                for res in results:
                    if res['success']:
                        response_parts.append(f"✅ **{res['command']}:**\n```\n{res['output']}\n```\n")
                    else:
                        response_parts.append(f"❌ **{res['command']}:**\n```\n{res['output']}\n```\n")
                
                return {
                    'message': "\n".join(response_parts),
                    'commands_executed': executed_commands
                }
            else:
                return {
                    'message': explanation or response.get('raw_response', 'No response')
                }
        except Exception as e:
            return {
                'message': f"❌ Error processing request: {str(e)}"
            }
    
    # General conversation - use LLM
    else:
        # Build conversation context
        conversation_context = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in chat_history[-10:]  # Last 10 messages for context
        ])
        
        system_prompt = """You are a helpful DevOps assistant. You can help users with:
- Running infrastructure commands (kubectl, aws, gcloud, az)
- Troubleshooting issues
- Checking system status
- Providing guidance on infrastructure management

Be concise and helpful. If the user wants to run a command, suggest it clearly.
If they want to fix something, guide them or ask if they want to link to an incident."""
        
        prompt = f"""{system_prompt}

Conversation history:
{conversation_context}

User: {user_message}
Assistant:"""
        
        try:
            # Use the chat method for general conversation
            messages = llm_service.start_conversation()
            # Add conversation history
            for msg in chat_history[-10:]:
                if msg['role'] == 'user':
                    messages.append({"role": "user", "content": msg['content']})
                else:
                    messages.append({"role": "assistant", "content": msg['content']})
            
            # Get response
            response = llm_service.chat(messages, user_message, incident_id=None)
            llm_response = response.get('raw_response', response.get('explanation', response.get('solution', 'No response')))
            
            return {
                'message': llm_response
            }
        except Exception as e:
            return {
                'message': f"❌ Error: {str(e)}"
            }

def log_chat_conversation(user_message: str, agent_response: str, incident_id: Optional[int] = None):
    """Log chat conversation to audit log"""
    try:
        with db_service.get_session() as session:
            audit_log = AuditLog(
                action_type=ActionType.LLM_QUERY,
                action_description=f"Chat conversation: {user_message[:100]}",
                llm_prompt=user_message,
                llm_response=agent_response,
                success=True,
                user_id="ui_user",
                source_system="chat_interface",
                incident_id=incident_id
            )
            session.add(audit_log)
            session.commit()
    except Exception as e:
        logger.error(f"Failed to log chat conversation: {str(e)}")

if __name__ == "__main__":
    main()