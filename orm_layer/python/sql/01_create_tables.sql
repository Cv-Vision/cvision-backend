-- This script creates the initial tables for the job application system.

-- Enable the 'uuid-ossp' extension for generating UUIDs.
-- This is necessary for the UUID columns with the default value.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------
-- Table: users
--
-- This table stores the users.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

-- -----------------------------------------------------------
-- Table: job_postings
--
-- This table stores information about job opportunities.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_postings (
    posting_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_by_user_id VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    location VARCHAR(100),
    experience_level VARCHAR(50),
    english_level VARCHAR(50),
    contract_type VARCHAR(50),
    industry_experience JSONB,
    additional_requirements JSONB,
    status VARCHAR(50) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key to link job postings to their creator.
    CONSTRAINT fk_user
      FOREIGN KEY (created_by_user_id)
      REFERENCES users (user_id)
);

-- -----------------------------------------------------------
-- Table: job_applications
--
-- This table stores user applications for specific job postings.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_applications (
    application_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_posting_id UUID NOT NULL,
    application_source VARCHAR(50) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    cv_upload_key VARCHAR(1024),
    cv_hash VARCHAR(255) UNIQUE,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key to link applications to a specific job posting.
    -- If a job posting is deleted, its applications will also be deleted.
    CONSTRAINT fk_job_posting
      FOREIGN KEY (job_posting_id)
      REFERENCES job_postings (posting_id)
      ON DELETE CASCADE,

    -- Foreign key to link applications to a candidate user.
    CONSTRAINT fk_user_application
      FOREIGN KEY (user_id)
      REFERENCES users (user_id)
      ON DELETE CASCADE
);

-- Index to improve lookup performance by CV hash.
CREATE INDEX IF NOT EXISTS idx_job_applications_cv_hash ON job_applications (cv_hash);

-- -----------------------------------------------------------
-- Table: cv_analysis_results
--
-- This table stores the results of the analysis of a CV.
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cv_analysis_results (
    analysis_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_application_id UUID NOT NULL,
    analysis_data JSONB,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key to link analysis results to a specific job application.
    -- If an application is deleted, its analysis result will also be deleted.
    CONSTRAINT fk_job_application
      FOREIGN KEY (job_application_id)
      REFERENCES job_applications (application_id)
      ON DELETE CASCADE
);