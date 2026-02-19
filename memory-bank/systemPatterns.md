# System Patterns: H.A.C.A - Home Assistant Config Auditor

## System Architecture

### Core Architecture Pattern
H.A.C.A follows a **Modular Analyzer Architecture** with the following key patterns:

#### 1. Analyzer Pattern
Each analyzer follows a consistent interface and structure:
- **AutomationAnalyzer**: Deep analysis of automations.yaml, scripts.yaml, scenes.yaml
- **EntityAnalyzer**: Monitors entity states and automation performance
- **PerformanceAnalyzer**: Tracks trigger rates and identifies performance issues
- **SecurityAnalyzer**: Detects hardcoded secrets and security vulnerabilities

**Common Analyzer Interface:**
```python
class BaseAnalyzer:
    async def analyze_all(self) -> list[dict[str, Any]]
    def get_issue_summary(self) -> dict[str, Any]
    def _analyze_entity(self, entity_id: str, config: dict) -> None
```

#### 2. Coordinator Pattern
Uses Home Assistant's `DataUpdateCoordinator` for:
- Scheduled scanning (configurable interval)
- Data aggregation from all analyzers
- Health score calculation
- State management and updates

#### 3. Service Pattern
Modular service registration system:
- Core services: `scan_all`, `scan_automations`, `scan_entities`
- Module 4 services: `generate_report`, `list_reports`, `get_report_content`
- Module 5 services: `fix_device_id`, `preview_device_id`, `list_backups`, etc.

#### 4. Sensor Pattern
Diagnostic sensors for health monitoring:
- `sensor.haca_health_score`: Overall configuration health percentage
- `sensor.haca_total_issues`: Total number of issues across all analyzers
- Individual issue count sensors for each analyzer type

## Key Component Relationships

### Data Flow Architecture
```
Configuration Files (YAML)
    ↓
Analyzers (Automation, Entity, Performance, Security)
    ↓
Data Coordinator (Aggregation & Health Score)
    ↓
Sensors (Health Monitoring)
    ↓
Web Interface (User Dashboard)
```

### Module Dependencies
- **Core Module**: Base functionality, analyzers, sensors
- **Module 4 (Compliance Report)**: PDF/HTML report generation
- **Module 5 (Refactoring Assistant)**: Automated fixes and backups
- **Optional Modules**: Can be enabled/disabled independently

## Critical Implementation Paths

### 1. Configuration Analysis Pipeline
```
1. Load YAML files (automations.yaml, scripts.yaml, scenes.yaml)
2. Parse and validate configurations
3. Run specialized analyzers on each configuration
4. Aggregate issues with severity classification
5. Calculate health score using progressive formula
6. Update coordinator data and sensors
```

### 2. Real-time Issue Detection
```
1. Subscribe to Home Assistant events (automation_reloaded, etc.)
2. Trigger quick analysis after configuration changes
3. Compare against known issues to detect new problems
4. Fire custom events for UI notifications
5. Update persistent notifications
```

### 3. Automated Refactoring Pipeline
```
1. User requests fix via service call
2. Generate preview of changes (dry run)
3. Create backup of current configuration
4. Apply changes with error handling
5. Validate changes and restore if needed
6. Update issue tracking
```

## Design Patterns in Use

### 1. Observer Pattern
- **Event Listeners**: Monitor Home Assistant configuration changes
- **Real-time Updates**: Automatic issue detection and notification
- **State Changes**: Track entity state changes for performance analysis

### 2. Strategy Pattern
- **Analyzer Selection**: Different strategies for different configuration types
- **Fix Strategies**: Different approaches for different issue types
- **Report Formats**: Multiple output formats (PDF, HTML, JSON)

### 3. Factory Pattern
- **Issue Creation**: Standardized issue object creation
- **Service Registration**: Dynamic service registration based on enabled modules
- **Analyzer Instantiation**: Factory methods for analyzer creation

### 4. Command Pattern
- **Service Calls**: Encapsulated operations with undo/redo capabilities
- **Fix Operations**: Atomic operations with rollback support
- **Backup Operations**: Command objects for backup/restore operations

## Component Relationships

### Core Components
- **`__init__.py`**: Main integration setup and service registration
- **`automation_analyzer.py`**: Deep automation analysis and device_id detection
- **`entity_analyzer.py`**: Entity health monitoring and performance tracking
- **`performance_analyzer.py`**: Trigger rate analysis and loop detection
- **`security_analyzer.py`**: Security vulnerability detection

### Web Interface Components
- **`custom_panel.py`**: Sidebar panel registration and management
- **`websocket.py`**: Real-time communication between frontend and backend
- **`www/haca-panel.js`**: Frontend JavaScript for the web interface

### Optional Modules
- **`report_generator.py`**: PDF/HTML report generation (Module 4)
- **`refactoring_assistant.py`**: Automated fixes and backup management (Module 5)

### Support Components
- **`conversation.py`**: AI integration for issue explanations
- **`translation_utils.py`**: Multi-language support
- **`sensor.py`**: Diagnostic sensor implementations

## Error Handling Patterns

### 1. Graceful Degradation
- Analyzers continue working even if one fails
- Services provide fallback responses
- UI shows partial results if some data is unavailable

### 2. Backup and Recovery
- Automatic backup creation before any configuration changes
- Rollback capabilities for failed operations
- Configuration validation before applying changes

### 3. User Safety
- All destructive operations require user confirmation
- Dry-run capabilities for previewing changes
- Clear warnings for potentially disruptive operations

## Performance Considerations

### 1. Resource Management
- Configurable scan intervals to balance performance vs. freshness
- Background task execution to avoid blocking the main thread
- Memory-efficient issue storage and processing

### 2. Scalability Patterns
- Modular design allows selective analyzer execution
- Lazy loading of optional modules
- Efficient YAML parsing and configuration caching

### 3. Real-time Processing
- Event-driven architecture for immediate issue detection
- Debounced configuration change detection
- Efficient issue comparison algorithms

## Integration Patterns

### 1. Home Assistant Integration
- Uses standard Home Assistant patterns and APIs
- Integrates with existing configuration management
- Leverages Home Assistant's service and event systems

### 2. HACS Distribution
- Follows HACS custom integration patterns
- Automatic updates through HACS
- Proper manifest and metadata configuration

### 3. External Service Integration
- AI conversation agent integration for explanations
- Optional integration with external security scanning tools
- Report generation with external libraries (fpdf2)

This architecture provides a robust, extensible foundation for configuration auditing while maintaining safety and performance in the Home Assistant ecosystem.