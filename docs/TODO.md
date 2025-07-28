# TODO - Monzo App

## High Priority

### 🔧 Automation System
- [ ] **Review automation triggers** - Auto topup not firing on X minutes. Review the rest to make sure all trigger types work correctly
  - [ ] Test minute-based triggers for auto topup
  - [ ] Verify hourly triggers work properly
  - [ ] Check daily triggers functionality
  - [ ] Validate balance threshold triggers
  - [ ] Test transaction-based triggers
  - [ ] Review autosorter trigger types (payday_date, time_of_day, transaction_based, date_range)
  - [ ] Verify pot sweep triggers
  - [ ] Check bills pot logic triggers

### 🐛 Bug Fixes
- [ ] **Investigate false execution results** - UI still showing "money moved" when no actual transfers occurred
  - [ ] Check if execution history is being properly stored in database
  - [ ] Verify UI is correctly reading execution history vs last_executed timestamp
  - [ ] Debug why successful execution is being reported when transfers fail
  - [ ] Test execution result tracking with real automation runs
- [ ] **Investigate web sockets** - Research and implement real-time updates
  - [ ] Research web socket libraries (Socket.IO, Flask-SocketIO, etc.)
  - [ ] Design real-time update architecture
  - [ ] Implement web socket server for live automation status
  - [ ] Add real-time UI updates for automation execution
  - [ ] Test web socket performance and reliability
- [ ] Fix timezone issues in automation execution
- [ ] Resolve circular import issues in automation modules
- [ ] Fix execution result tracking for all automation types

### 🧪 Testing
- [ ] Create comprehensive test suite for automation triggers
- [ ] Test all trigger types with real data
- [ ] Verify execution result accuracy

## Medium Priority

### 📊 UI/UX Improvements
- [ ] Add execution history view for automation rules
- [ ] Improve error display in automation management
- [ ] Add real-time status updates for automation execution

### 🔍 Monitoring & Logging
- [ ] Add detailed logging for automation trigger evaluation
- [ ] Create monitoring dashboard for automation health
- [ ] Add alerting for failed automation executions

## Low Priority

### 📚 Documentation
- [ ] Update automation trigger documentation
- [ ] Add troubleshooting guide for automation issues
- [ ] Create user guide for setting up automation rules

### 🚀 Performance
- [ ] Optimize automation trigger evaluation
- [ ] Add caching for frequently accessed data
- [ ] Implement batch processing for automation rules 