CREATE SCHEMA "public";

CREATE  TABLE users ( 
	id                   integer GENERATED ALWAYS AS IDENTITY  NOT NULL ,
	telegram_id          text  NOT NULL ,
	timezone             varchar(100) DEFAULT 'Etc/UTC'  ,
	CONSTRAINT pk_users_id PRIMARY KEY ( id ),
	CONSTRAINT idx_users UNIQUE ( telegram_id ) 
 );

CREATE  TABLE repos ( 
	id                   integer GENERATED ALWAYS AS IDENTITY  NOT NULL ,
	url                  text  NOT NULL ,
	login                text   ,
	pass                 text   ,
	last_checkout        timestamp DEFAULT CURRENT_TIMESTAMP  ,
	user_id              integer  NOT NULL ,
	CONSTRAINT pk_repos PRIMARY KEY ( url, user_id )
 );

CREATE INDEX idx_repos_user_id ON repos ( user_id );

CREATE INDEX idx_repos_id ON repos ( id );

COMMENT ON COLUMN repos.url IS 'Repo url';

COMMENT ON COLUMN repos.login IS 'Repo login';

COMMENT ON COLUMN repos.pass IS 'Repo pass or token';

COMMENT ON COLUMN repos.last_checkout IS 'Last time, when checked new commits';

CREATE  TABLE user_states ( 
	user_id              integer  NOT NULL ,
	scenario_name        varchar(100)  NOT NULL ,
	scenario_step        varchar(100)  NOT NULL ,
	CONSTRAINT pk_user_states_user_id PRIMARY KEY ( user_id )
 );

ALTER TABLE repos ADD CONSTRAINT fk_repos_users FOREIGN KEY ( user_id ) REFERENCES users( id ) ON DELETE CASCADE;

ALTER TABLE user_states ADD CONSTRAINT fk_user_states_users FOREIGN KEY ( user_id ) REFERENCES users( id ) ON DELETE CASCADE;

