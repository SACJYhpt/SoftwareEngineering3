-- R3 schema reference for a NEW EMPTY MySQL 8.4 database only.
-- NOT an upgrade/migration script. Do not apply to an existing team database.
-- Existing R2 data needs reviewed ALTER/backfill/constraint changes; see R3 handoff.
-- No accounts, credentials, SMTP configuration or demo data are included.



CREATE TABLE account_requests (
	email VARCHAR(254) NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	requested_at DATETIME NOT NULL, 
	PRIMARY KEY (email, purpose)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE backup_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	created_at DATETIME NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	filename VARCHAR(255), 
	error VARCHAR(255), 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_backup_records_created_at ON backup_records (created_at);


CREATE TABLE event_types (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	is_active BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE login_throttles (
	email VARCHAR(254) NOT NULL, 
	failed_count INTEGER NOT NULL, 
	locked_until DATETIME, 
	PRIMARY KEY (email)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE published_documents (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	kind VARCHAR(20) NOT NULL, 
	version INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	published_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_version UNIQUE (kind, version)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_published_documents_kind ON published_documents (kind);


CREATE TABLE registration_workflow_locks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE revoked_tokens (
	jti VARCHAR(64) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (jti)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE units (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	is_active BOOL NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_unit_kind CHECK (kind IN ('department', 'office', 'club'))
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	email VARCHAR(254) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	is_active BOOL NOT NULL, 
	identity VARCHAR(20), 
	department_id INTEGER, 
	grade INTEGER, 
	email_verified BOOL NOT NULL DEFAULT 0, 
	token_version INTEGER NOT NULL DEFAULT 0, 
	consent_at DATETIME, 
	privacy_version INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_role CHECK (role IN ('member', 'manager', 'admin')), 
	CONSTRAINT ck_user_identity CHECK (identity IS NULL OR identity IN ('student', 'teacher', 'staff')), 
	UNIQUE (email), 
	FOREIGN KEY(department_id) REFERENCES units (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE account_tokens (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	token_hash VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	used_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_account_tokens_user_id ON account_tokens (user_id);


CREATE TABLE audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	actor_id INTEGER NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	target VARCHAR(191) NOT NULL, 
	recorded_at DATETIME NOT NULL, 
	details JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);

CREATE INDEX ix_audit_logs_recorded_at ON audit_logs (recorded_at);


CREATE TABLE events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	unit_id INTEGER NOT NULL, 
	owner_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	category VARCHAR(100) NOT NULL, 
	location VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	contact_information VARCHAR(255) NOT NULL, 
	notes TEXT, 
	starts_at DATETIME NOT NULL, 
	ends_at DATETIME NOT NULL, 
	registration_opens_at DATETIME NOT NULL, 
	registration_closes_at DATETIME NOT NULL, 
	capacity INTEGER, 
	is_public BOOL NOT NULL, 
	is_cancelled BOOL NOT NULL, 
	cancellation_reason TEXT, 
	cancelled_at DATETIME, 
	waitlist_enabled BOOL NOT NULL DEFAULT 0, 
	waitlist_capacity INTEGER, 
	eligibility_identities JSON NOT NULL, 
	eligibility_department_ids JSON NOT NULL, 
	eligibility_grades JSON NOT NULL, 
	check_in_used BOOL NOT NULL DEFAULT 0, 
	notification_revision INTEGER NOT NULL DEFAULT 0, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_event_capacity CHECK (capacity IS NULL OR capacity > 0), 
	CONSTRAINT ck_event_time CHECK (ends_at > starts_at), 
	CONSTRAINT ck_registration_time CHECK (registration_opens_at < registration_closes_at), 
	CONSTRAINT ck_registration_before_event CHECK (registration_closes_at <= starts_at), 
	CONSTRAINT ck_event_waitlist CHECK (NOT waitlist_enabled OR (capacity IS NOT NULL AND waitlist_capacity > 0)), 
	FOREIGN KEY(unit_id) REFERENCES units (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_events_starts_at ON events (starts_at);

CREATE INDEX ix_events_unit_id ON events (unit_id);


CREATE TABLE organizer_acknowledgements (
	user_id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	acknowledged_at DATETIME NOT NULL, 
	PRIMARY KEY (user_id, document_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(document_id) REFERENCES published_documents (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;


CREATE TABLE unit_managers (
	user_id INTEGER NOT NULL, 
	unit_id INTEGER NOT NULL, 
	PRIMARY KEY (user_id, unit_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(unit_id) REFERENCES units (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_unit_managers_unit_id ON unit_managers (unit_id);


CREATE TABLE registrations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	registered_at DATETIME NOT NULL, 
	status VARCHAR(20) NOT NULL DEFAULT 'registered', 
	cancelled_at DATETIME, 
	attendance_status VARCHAR(20) NOT NULL DEFAULT 'unrecorded', 
	waitlisted_at DATETIME, 
	checked_in_at DATETIME, 
	cancellation_reason TEXT, 
	revision INTEGER NOT NULL DEFAULT 0, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_registration_user_event UNIQUE (user_id, event_id), 
	CONSTRAINT ck_registration_status CHECK (status IN ('registered', 'cancelled', 'waitlisted', 'not_promoted')), 
	CONSTRAINT ck_waitlist_timestamp CHECK (status != 'waitlisted' OR waitlisted_at IS NOT NULL), 
	CONSTRAINT ck_registration_attendance CHECK (attendance_status IN ('unrecorded', 'present', 'absent', 'leave')), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_registrations_event_id ON registrations (event_id);

CREATE INDEX ix_registrations_status ON registrations (status);

CREATE INDEX ix_registrations_user_id ON registrations (user_id);


CREATE TABLE cancellation_requests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	registration_id INTEGER NOT NULL, 
	active_registration_id INTEGER, 
	reason TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	submitted_at DATETIME NOT NULL, 
	auto_approve_at DATETIME NOT NULL, 
	reminder_sent_at DATETIME, 
	processed_at DATETIME, 
	reviewed_by INTEGER, 
	rejection_reason TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_cancellation_request_status CHECK (status IN ('pending', 'approved', 'rejected', 'auto_approved')), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id), 
	UNIQUE (active_registration_id), 
	FOREIGN KEY(active_registration_id) REFERENCES registrations (id), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_cancellation_requests_auto_approve_at ON cancellation_requests (auto_approve_at);

CREATE INDEX ix_cancellation_requests_registration_id ON cancellation_requests (registration_id);


CREATE TABLE outgoing_emails (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	recipient VARCHAR(254) NOT NULL, 
	subject VARCHAR(255) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	attempts INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	next_attempt_at DATETIME NOT NULL, 
	sent_at DATETIME, 
	deduplication_key VARCHAR(191), 
	kind VARCHAR(30), 
	registration_id INTEGER, 
	event_revision INTEGER, 
	event_start_at DATETIME, 
	registration_revision INTEGER, 
	reschedule_notice BOOL NOT NULL DEFAULT 0, 
	PRIMARY KEY (id), 
	UNIQUE (deduplication_key), 
	FOREIGN KEY(registration_id) REFERENCES registrations (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_outgoing_emails_next_attempt_at ON outgoing_emails (next_attempt_at);

CREATE INDEX ix_outgoing_emails_registration_id ON outgoing_emails (registration_id);

CREATE INDEX ix_outgoing_emails_status ON outgoing_emails (status);


CREATE TABLE email_attempts (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	email_id INTEGER NOT NULL, 
	attempted_at DATETIME NOT NULL, 
	error VARCHAR(255), 
	PRIMARY KEY (id), 
	FOREIGN KEY(email_id) REFERENCES outgoing_emails (id)
)ENGINE=InnoDB CHARSET=utf8mb4

;

CREATE INDEX ix_email_attempts_email_id ON email_attempts (email_id);
