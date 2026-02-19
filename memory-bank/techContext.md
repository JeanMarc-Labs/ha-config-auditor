# Technical Context: H.A.C.A - Home Assistant Config Auditor

## Technologies Used

### Core Technologies
- **Python 3.10+**: Primary programming language with modern features
- **Home Assistant Custom Component Framework**: Integration with Home Assistant ecosystem
- **PyYAML 6.0+**: YAML configuration file parsing and manipulation
- **fpdf2 2.7.4+**: PDF report generation for compliance reports

### Frontend Technologies
- **JavaScript ES6+**: Custom web panel implementation
- **Home Assistant Lovelace Framework**: Integration with HA's UI system
- **WebSocket API**: Real-time communication between frontend and backend

### Development Tools
- **HACS (Home Assistant Community Store)**: Distribution and update mechanism
- **Voluptuous**: Configuration validation and schema definition
- **Home Assistant DataUpdateCoordinator**: State management and scheduled updates

## Development Setup

### Prerequisites
- **Home Assistant**: Version compatible with custom components
- **Python 3.10+**: Required for modern Python features
- **HACS**: For easy installation and updates

### Installation Methods
1. **HACS (Recommended)**: Automatic installation through Home Assistant Community Store
2. **Manual**: Copy custom_components/config_auditor to Home Assistant config directory

### Configuration Requirements
- **File System Access**: Read access to configuration files (automations.yaml, scripts.yaml, scenes.yaml)
- **Entity Registry Access**: Read access to Home Assistant entity registry
- **Service Registration**: Permission to register custom services

## Technical Constraints

### Performance Constraints
- **Configuration File Size**: Must handle large configuration files efficiently
- **Scan Frequency**: Configurable intervals to balance performance vs. freshness
- **Memory Usage**: Efficient memory management for issue storage and processing
- **Real-time Processing**: Event-driven architecture for immediate issue detection

### Security Constraints
- **File System Access**: Limited to Home Assistant configuration directory
- **Configuration Modification**: All changes require user confirmation
- **Backup Requirements**: Automatic backup creation before any modifications
- **Validation**: Configuration validation before applying changes

### Integration Constraints
- **Home Assistant Version Compatibility**: Must work with supported HA versions
- **HACS Requirements**: Follow HACS custom integration guidelines
- **Service Registration**: Limited to approved service names and schemas
- **Event System**: Must use standard Home Assistant event patterns

## Dependencies

### Required Dependencies
```python
{
    "PyYAML": ">=6.0",
    "fpdf2": ">=2.7.4"
}
```

### Optional Dependencies
- **AI Conversation Agents**: OpenAI, Google Generative AI for explanations
- **External Security Tools**: Optional integration for enhanced security scanning

### Development Dependencies
- **pytest**: Testing framework
- **black**: Code formatting
- **mypy**: Type checking
- **ruff**: Linting and code quality

## Code Structure and Organization

### Package Structure
```
custom_components/config_auditor/
├── __init__.py              # Main integration setup
├── automation_analyzer.py   # Automation analysis
├── entity_analyzer.py       # Entity health monitoring
├── performance_analyzer.py  # Performance analysis
├── security_analyzer.py     # Security vulnerability detection
├── report_generator.py      # PDF/HTML report generation (Module 4)
├── refactoring_assistant.py # Automated fixes (Module 5)
├── custom_panel.py          # Web interface registration
├── websocket.py             # Real-time communication
├── conversation.py          # AI integration
├── translation_utils.py     # Multi-language support
├── sensor.py               # Diagnostic sensors
├── config_flow.py          # Configuration flow
├── manifest.json           # Integration metadata
├── services.yaml           # Service definitions
├── strings.json            # UI strings
├── translations/           # Multi-language translations
└── www/                    # Frontend assets
    └── haca-panel.js       # Web panel implementation
```

### Module Organization
- **Core Module**: Base functionality, analyzers, sensors
- **Module 4**: Compliance reporting (PDF/HTML generation)
- **Module 5**: Refactoring assistant (automated fixes)
- **Optional Modules**: Can be enabled/disabled independently

## Configuration Patterns

### Configuration Schema
```python
CONFIG_SCHEMA = vol.Schema({
    vol.Optional("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    vol.Optional("enable_reports", default=True): cv.boolean,
    vol.Optional("enable_refactoring", default=True): cv.boolean,
    vol.Optional("backup_retention_days", default=30): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
})
```

### Service Definitions
- **Core Services**: `scan_all`, `scan_automations`, `scan_entities`
- **Report Services**: `generate_report`, `list_reports`, `get_report_content`
- **Refactoring Services**: `fix_device_id`, `preview_device_id`, `list_backups`, etc.

## Tool Usage Patterns

### YAML Processing
- **PyYAML**: Safe loading and parsing of configuration files
- **Validation**: Schema validation for configuration integrity
- **Backup**: YAML dump for configuration backup and restore

### File System Operations
- **Configuration Access**: Read-only access to HA configuration files
- **Backup Storage**: Dedicated backup directory with timestamped files
- **Report Generation**: PDF/HTML report creation in reports directory

### Home Assistant Integration
- **Entity Registry**: Access to entity metadata and relationships
- **State Management**: Real-time state monitoring and tracking
- **Service Calls**: Integration with existing Home Assistant services
- **Event System**: Subscription to configuration change events

## Development Patterns

### Error Handling
- **Graceful Degradation**: Continue operation even if individual components fail
- **User Safety**: All destructive operations require confirmation
- **Backup and Recovery**: Automatic backup creation and rollback capabilities

### Testing Strategy
- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end workflow testing
- **Configuration Testing**: Test with various configuration file formats
- **Performance Testing**: Large configuration file handling

### Code Quality
- **Type Hints**: Comprehensive type annotations
- **Documentation**: Detailed docstrings and inline comments
- **Code Formatting**: Consistent formatting with black
- **Linting**: Code quality checks with ruff

## Performance Optimization

### Memory Management
- **Efficient Data Structures**: Optimized issue storage and retrieval
- **Lazy Loading**: Load components only when needed
- **Caching**: Configuration parsing and analysis results caching

### Processing Optimization
- **Background Tasks**: Non-blocking analysis operations
- **Incremental Updates**: Update only changed data
- **Parallel Processing**: Concurrent analysis where possible

### Resource Management
- **Configurable Intervals**: User-configurable scan frequencies
- **Resource Monitoring**: Track memory and CPU usage
- **Cleanup Operations**: Regular cleanup of temporary files and data

This technical context provides the foundation for understanding the implementation details, constraints, and patterns used in the H.A.C.A project.