PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE `migration_log` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `migration_id` TEXT NOT NULL
, `sql` TEXT NOT NULL
, `success` INTEGER NOT NULL
, `error` TEXT NOT NULL
, `timestamp` DATETIME NOT NULL
);
INSERT INTO migration_log VALUES(1,'create migration_log table',replace('CREATE TABLE IF NOT EXISTS `migration_log` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `migration_id` TEXT NOT NULL\n, `sql` TEXT NOT NULL\n, `success` INTEGER NOT NULL\n, `error` TEXT NOT NULL\n, `timestamp` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(2,'create user table',replace('CREATE TABLE IF NOT EXISTS `user` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `login` TEXT NOT NULL\n, `email` TEXT NOT NULL\n, `name` TEXT NULL\n, `password` TEXT NULL\n, `salt` TEXT NULL\n, `rands` TEXT NULL\n, `company` TEXT NULL\n, `account_id` INTEGER NOT NULL\n, `is_admin` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(3,'add unique index user.login','CREATE UNIQUE INDEX `UQE_user_login` ON `user` (`login`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(4,'add unique index user.email','CREATE UNIQUE INDEX `UQE_user_email` ON `user` (`email`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(5,'drop index UQE_user_login - v1','DROP INDEX `UQE_user_login`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(6,'drop index UQE_user_email - v1','DROP INDEX `UQE_user_email`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(7,'Rename table user to user_v1 - v1','ALTER TABLE `user` RENAME TO `user_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(8,'create user table v2',replace('CREATE TABLE IF NOT EXISTS `user` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `login` TEXT NOT NULL\n, `email` TEXT NOT NULL\n, `name` TEXT NULL\n, `password` TEXT NULL\n, `salt` TEXT NULL\n, `rands` TEXT NULL\n, `company` TEXT NULL\n, `org_id` INTEGER NOT NULL\n, `is_admin` INTEGER NOT NULL\n, `email_verified` INTEGER NULL\n, `theme` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(9,'create index UQE_user_login - v2','CREATE UNIQUE INDEX `UQE_user_login` ON `user` (`login`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(10,'create index UQE_user_email - v2','CREATE UNIQUE INDEX `UQE_user_email` ON `user` (`email`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(11,'copy data_source v1 to v2',replace('INSERT INTO `user` (`org_id`\n, `created`\n, `login`\n, `name`\n, `rands`\n, `password`\n, `salt`\n, `company`\n, `is_admin`\n, `updated`\n, `id`\n, `version`\n, `email`) SELECT `account_id`\n, `created`\n, `login`\n, `name`\n, `rands`\n, `password`\n, `salt`\n, `company`\n, `is_admin`\n, `updated`\n, `id`\n, `version`\n, `email` FROM `user_v1`','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(12,'Drop old table user_v1','DROP TABLE IF EXISTS `user_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(13,'Add column help_flags1 to user table','alter table `user` ADD COLUMN `help_flags1` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(14,'Update user table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(15,'Add last_seen_at column to user','alter table `user` ADD COLUMN `last_seen_at` DATETIME NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(16,'Add missing user data','code migration',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(17,'Add is_disabled column to user','alter table `user` ADD COLUMN `is_disabled` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(18,'create temp user table v1-7',replace('CREATE TABLE IF NOT EXISTS `temp_user` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `email` TEXT NOT NULL\n, `name` TEXT NULL\n, `role` TEXT NULL\n, `code` TEXT NOT NULL\n, `status` TEXT NOT NULL\n, `invited_by_user_id` INTEGER NULL\n, `email_sent` INTEGER NOT NULL\n, `email_sent_on` DATETIME NULL\n, `remote_addr` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(19,'create index IDX_temp_user_email - v1-7','CREATE INDEX `IDX_temp_user_email` ON `temp_user` (`email`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(20,'create index IDX_temp_user_org_id - v1-7','CREATE INDEX `IDX_temp_user_org_id` ON `temp_user` (`org_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(21,'create index IDX_temp_user_code - v1-7','CREATE INDEX `IDX_temp_user_code` ON `temp_user` (`code`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(22,'create index IDX_temp_user_status - v1-7','CREATE INDEX `IDX_temp_user_status` ON `temp_user` (`status`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(23,'Update temp_user table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(24,'create star table',replace('CREATE TABLE IF NOT EXISTS `star` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `user_id` INTEGER NOT NULL\n, `dashboard_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(25,'add unique index star.user_id_dashboard_id','CREATE UNIQUE INDEX `UQE_star_user_id_dashboard_id` ON `star` (`user_id`,`dashboard_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(26,'create org table v1',replace('CREATE TABLE IF NOT EXISTS `org` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `name` TEXT NOT NULL\n, `address1` TEXT NULL\n, `address2` TEXT NULL\n, `city` TEXT NULL\n, `state` TEXT NULL\n, `zip_code` TEXT NULL\n, `country` TEXT NULL\n, `billing_email` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(27,'create index UQE_org_name - v1','CREATE UNIQUE INDEX `UQE_org_name` ON `org` (`name`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(28,'create org_user table v1',replace('CREATE TABLE IF NOT EXISTS `org_user` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `user_id` INTEGER NOT NULL\n, `role` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(29,'create index IDX_org_user_org_id - v1','CREATE INDEX `IDX_org_user_org_id` ON `org_user` (`org_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(30,'create index UQE_org_user_org_id_user_id - v1','CREATE UNIQUE INDEX `UQE_org_user_org_id_user_id` ON `org_user` (`org_id`,`user_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(31,'Update org table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(32,'Update org_user table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(33,'Migrate all Read Only Viewers to Viewers','UPDATE org_user SET role = ''Viewer'' WHERE role = ''Read Only Editor''',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(34,'create dashboard table',replace('CREATE TABLE IF NOT EXISTS `dashboard` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `slug` TEXT NOT NULL\n, `title` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `account_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(35,'add index dashboard.account_id','CREATE INDEX `IDX_dashboard_account_id` ON `dashboard` (`account_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(36,'add unique index dashboard_account_id_slug','CREATE UNIQUE INDEX `UQE_dashboard_account_id_slug` ON `dashboard` (`account_id`,`slug`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(37,'create dashboard_tag table',replace('CREATE TABLE IF NOT EXISTS `dashboard_tag` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `dashboard_id` INTEGER NOT NULL\n, `term` TEXT NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(38,'add unique index dashboard_tag.dasboard_id_term','CREATE UNIQUE INDEX `UQE_dashboard_tag_dashboard_id_term` ON `dashboard_tag` (`dashboard_id`,`term`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(39,'drop index UQE_dashboard_tag_dashboard_id_term - v1','DROP INDEX `UQE_dashboard_tag_dashboard_id_term`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(40,'Rename table dashboard to dashboard_v1 - v1','ALTER TABLE `dashboard` RENAME TO `dashboard_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(41,'create dashboard v2',replace('CREATE TABLE IF NOT EXISTS `dashboard` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `slug` TEXT NOT NULL\n, `title` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(42,'create index IDX_dashboard_org_id - v2','CREATE INDEX `IDX_dashboard_org_id` ON `dashboard` (`org_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(43,'create index UQE_dashboard_org_id_slug - v2','CREATE UNIQUE INDEX `UQE_dashboard_org_id_slug` ON `dashboard` (`org_id`,`slug`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(44,'copy dashboard v1 to v2',replace('INSERT INTO `dashboard` (`org_id`\n, `created`\n, `updated`\n, `id`\n, `version`\n, `slug`\n, `title`\n, `data`) SELECT `account_id`\n, `created`\n, `updated`\n, `id`\n, `version`\n, `slug`\n, `title`\n, `data` FROM `dashboard_v1`','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(45,'drop table dashboard_v1','DROP TABLE IF EXISTS `dashboard_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(46,'alter dashboard.data to mediumtext v1','SELECT 0;',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(47,'Add column updated_by in dashboard - v2','alter table `dashboard` ADD COLUMN `updated_by` INTEGER NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(48,'Add column created_by in dashboard - v2','alter table `dashboard` ADD COLUMN `created_by` INTEGER NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(49,'Add column gnetId in dashboard','alter table `dashboard` ADD COLUMN `gnet_id` INTEGER NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(50,'Add index for gnetId in dashboard','CREATE INDEX `IDX_dashboard_gnet_id` ON `dashboard` (`gnet_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(51,'Add column plugin_id in dashboard','alter table `dashboard` ADD COLUMN `plugin_id` TEXT NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(52,'Add index for plugin_id in dashboard','CREATE INDEX `IDX_dashboard_org_id_plugin_id` ON `dashboard` (`org_id`,`plugin_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(53,'Add index for dashboard_id in dashboard_tag','CREATE INDEX `IDX_dashboard_tag_dashboard_id` ON `dashboard_tag` (`dashboard_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(54,'Update dashboard table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(55,'Update dashboard_tag table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(56,'Add column folder_id in dashboard','alter table `dashboard` ADD COLUMN `folder_id` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(57,'Add column isFolder in dashboard','alter table `dashboard` ADD COLUMN `is_folder` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(58,'Add column has_acl in dashboard','alter table `dashboard` ADD COLUMN `has_acl` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(59,'Add column uid in dashboard','alter table `dashboard` ADD COLUMN `uid` TEXT NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(60,'Update uid column values in dashboard','UPDATE dashboard SET uid=printf(''%09d'',id) WHERE uid IS NULL;',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(61,'Add unique index dashboard_org_id_uid','CREATE UNIQUE INDEX `UQE_dashboard_org_id_uid` ON `dashboard` (`org_id`,`uid`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(62,'Remove unique index org_id_slug','DROP INDEX `UQE_dashboard_org_id_slug`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(63,'Update dashboard title length','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(64,'Add unique index for dashboard_org_id_title_folder_id','CREATE UNIQUE INDEX `UQE_dashboard_org_id_folder_id_title` ON `dashboard` (`org_id`,`folder_id`,`title`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(65,'create dashboard_provisioning',replace('CREATE TABLE IF NOT EXISTS `dashboard_provisioning` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `dashboard_id` INTEGER NULL\n, `name` TEXT NOT NULL\n, `external_id` TEXT NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(66,'Rename table dashboard_provisioning to dashboard_provisioning_tmp_qwerty - v1','ALTER TABLE `dashboard_provisioning` RENAME TO `dashboard_provisioning_tmp_qwerty`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(67,'create dashboard_provisioning v2',replace('CREATE TABLE IF NOT EXISTS `dashboard_provisioning` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `dashboard_id` INTEGER NULL\n, `name` TEXT NOT NULL\n, `external_id` TEXT NOT NULL\n, `updated` INTEGER NOT NULL DEFAULT 0\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(68,'create index IDX_dashboard_provisioning_dashboard_id - v2','CREATE INDEX `IDX_dashboard_provisioning_dashboard_id` ON `dashboard_provisioning` (`dashboard_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(69,'create index IDX_dashboard_provisioning_dashboard_id_name - v2','CREATE INDEX `IDX_dashboard_provisioning_dashboard_id_name` ON `dashboard_provisioning` (`dashboard_id`,`name`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(70,'copy dashboard_provisioning v1 to v2',replace('INSERT INTO `dashboard_provisioning` (`name`\n, `external_id`\n, `id`\n, `dashboard_id`) SELECT `name`\n, `external_id`\n, `id`\n, `dashboard_id` FROM `dashboard_provisioning_tmp_qwerty`','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(71,'drop dashboard_provisioning_tmp_qwerty','DROP TABLE IF EXISTS `dashboard_provisioning_tmp_qwerty`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(72,'Add check_sum column','alter table `dashboard_provisioning` ADD COLUMN `check_sum` TEXT NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(73,'create data_source table',replace('CREATE TABLE IF NOT EXISTS `data_source` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `account_id` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `type` TEXT NOT NULL\n, `name` TEXT NOT NULL\n, `access` TEXT NOT NULL\n, `url` TEXT NOT NULL\n, `password` TEXT NULL\n, `user` TEXT NULL\n, `database` TEXT NULL\n, `basic_auth` INTEGER NOT NULL\n, `basic_auth_user` TEXT NULL\n, `basic_auth_password` TEXT NULL\n, `is_default` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(74,'add index data_source.account_id','CREATE INDEX `IDX_data_source_account_id` ON `data_source` (`account_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(75,'add unique index data_source.account_id_name','CREATE UNIQUE INDEX `UQE_data_source_account_id_name` ON `data_source` (`account_id`,`name`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(76,'drop index IDX_data_source_account_id - v1','DROP INDEX `IDX_data_source_account_id`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(77,'drop index UQE_data_source_account_id_name - v1','DROP INDEX `UQE_data_source_account_id_name`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(78,'Rename table data_source to data_source_v1 - v1','ALTER TABLE `data_source` RENAME TO `data_source_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(79,'create data_source table v2',replace('CREATE TABLE IF NOT EXISTS `data_source` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `type` TEXT NOT NULL\n, `name` TEXT NOT NULL\n, `access` TEXT NOT NULL\n, `url` TEXT NOT NULL\n, `password` TEXT NULL\n, `user` TEXT NULL\n, `database` TEXT NULL\n, `basic_auth` INTEGER NOT NULL\n, `basic_auth_user` TEXT NULL\n, `basic_auth_password` TEXT NULL\n, `is_default` INTEGER NOT NULL\n, `json_data` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(80,'create index IDX_data_source_org_id - v2','CREATE INDEX `IDX_data_source_org_id` ON `data_source` (`org_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(81,'create index UQE_data_source_org_id_name - v2','CREATE UNIQUE INDEX `UQE_data_source_org_id_name` ON `data_source` (`org_id`,`name`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(82,'copy data_source v1 to v2',replace('INSERT INTO `data_source` (`version`\n, `name`\n, `user`\n, `password`\n, `database`\n, `created`\n, `org_id`\n, `id`\n, `access`\n, `basic_auth`\n, `basic_auth_password`\n, `is_default`\n, `type`\n, `basic_auth_user`\n, `updated`\n, `url`) SELECT `version`\n, `name`\n, `user`\n, `password`\n, `database`\n, `created`\n, `account_id`\n, `id`\n, `access`\n, `basic_auth`\n, `basic_auth_password`\n, `is_default`\n, `type`\n, `basic_auth_user`\n, `updated`\n, `url` FROM `data_source_v1`','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(83,'Drop old table data_source_v1 #2','DROP TABLE IF EXISTS `data_source_v1`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(84,'Add column with_credentials','alter table `data_source` ADD COLUMN `with_credentials` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(85,'Add secure json data column','alter table `data_source` ADD COLUMN `secure_json_data` TEXT NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(86,'Update data_source table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(87,'Update initial version to 1','UPDATE data_source SET version = 1 WHERE version = 0',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(88,'Add read_only data column','alter table `data_source` ADD COLUMN `read_only` INTEGER NULL ',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(89,'Migrate logging ds to loki ds','UPDATE data_source SET type = ''loki'' WHERE type = ''logging''',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(90,'Update json_data with nulls','UPDATE data_source SET json_data = ''{}'' WHERE json_data is null',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(91,'create api_key table',replace('CREATE TABLE IF NOT EXISTS `api_key` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `account_id` INTEGER NOT NULL\n, `name` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `role` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(92,'add index api_key.account_id','CREATE INDEX `IDX_api_key_account_id` ON `api_key` (`account_id`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(93,'add index api_key.key','CREATE UNIQUE INDEX `UQE_api_key_key` ON `api_key` (`key`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(94,'add index api_key.account_id_name','CREATE UNIQUE INDEX `UQE_api_key_account_id_name` ON `api_key` (`account_id`,`name`);',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(95,'drop index IDX_api_key_account_id - v1','DROP INDEX `IDX_api_key_account_id`',1,'','2020-02-18 16:17:54');
INSERT INTO migration_log VALUES(96,'drop index UQE_api_key_key - v1','DROP INDEX `UQE_api_key_key`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(97,'drop index UQE_api_key_account_id_name - v1','DROP INDEX `UQE_api_key_account_id_name`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(98,'Rename table api_key to api_key_v1 - v1','ALTER TABLE `api_key` RENAME TO `api_key_v1`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(99,'create api_key table v2',replace('CREATE TABLE IF NOT EXISTS `api_key` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `name` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `role` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(100,'create index IDX_api_key_org_id - v2','CREATE INDEX `IDX_api_key_org_id` ON `api_key` (`org_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(101,'create index UQE_api_key_key - v2','CREATE UNIQUE INDEX `UQE_api_key_key` ON `api_key` (`key`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(102,'create index UQE_api_key_org_id_name - v2','CREATE UNIQUE INDEX `UQE_api_key_org_id_name` ON `api_key` (`org_id`,`name`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(103,'copy api_key v1 to v2',replace('INSERT INTO `api_key` (`id`\n, `org_id`\n, `name`\n, `key`\n, `role`\n, `created`\n, `updated`) SELECT `id`\n, `account_id`\n, `name`\n, `key`\n, `role`\n, `created`\n, `updated` FROM `api_key_v1`','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(104,'Drop old table api_key_v1','DROP TABLE IF EXISTS `api_key_v1`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(105,'Update api_key table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(106,'Add expires to api_key table','alter table `api_key` ADD COLUMN `expires` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(107,'create dashboard_snapshot table v4',replace('CREATE TABLE IF NOT EXISTS `dashboard_snapshot` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `name` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `dashboard` TEXT NOT NULL\n, `expires` DATETIME NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(108,'drop table dashboard_snapshot_v4 #1','DROP TABLE IF EXISTS `dashboard_snapshot`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(109,'create dashboard_snapshot table v5 #2',replace('CREATE TABLE IF NOT EXISTS `dashboard_snapshot` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `name` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `delete_key` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `user_id` INTEGER NOT NULL\n, `external` INTEGER NOT NULL\n, `external_url` TEXT NOT NULL\n, `dashboard` TEXT NOT NULL\n, `expires` DATETIME NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(110,'create index UQE_dashboard_snapshot_key - v5','CREATE UNIQUE INDEX `UQE_dashboard_snapshot_key` ON `dashboard_snapshot` (`key`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(111,'create index UQE_dashboard_snapshot_delete_key - v5','CREATE UNIQUE INDEX `UQE_dashboard_snapshot_delete_key` ON `dashboard_snapshot` (`delete_key`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(112,'create index IDX_dashboard_snapshot_user_id - v5','CREATE INDEX `IDX_dashboard_snapshot_user_id` ON `dashboard_snapshot` (`user_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(113,'alter dashboard_snapshot to mediumtext v2','SELECT 0;',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(114,'Update dashboard_snapshot table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(115,'Add column external_delete_url to dashboard_snapshots table','alter table `dashboard_snapshot` ADD COLUMN `external_delete_url` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(116,'create quota table v1',replace('CREATE TABLE IF NOT EXISTS `quota` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NULL\n, `user_id` INTEGER NULL\n, `target` TEXT NOT NULL\n, `limit` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(117,'create index UQE_quota_org_id_user_id_target - v1','CREATE UNIQUE INDEX `UQE_quota_org_id_user_id_target` ON `quota` (`org_id`,`user_id`,`target`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(118,'Update quota table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(119,'create plugin_setting table',replace('CREATE TABLE IF NOT EXISTS `plugin_setting` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NULL\n, `plugin_id` TEXT NOT NULL\n, `enabled` INTEGER NOT NULL\n, `pinned` INTEGER NOT NULL\n, `json_data` TEXT NULL\n, `secure_json_data` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(120,'create index UQE_plugin_setting_org_id_plugin_id - v1','CREATE UNIQUE INDEX `UQE_plugin_setting_org_id_plugin_id` ON `plugin_setting` (`org_id`,`plugin_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(121,'Add column plugin_version to plugin_settings','alter table `plugin_setting` ADD COLUMN `plugin_version` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(122,'Update plugin_setting table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(123,'create session table',replace('CREATE TABLE IF NOT EXISTS `session` (\n`key` TEXT PRIMARY KEY NOT NULL\n, `data` BLOB NOT NULL\n, `expiry` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(124,'Drop old table playlist table','DROP TABLE IF EXISTS `playlist`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(125,'Drop old table playlist_item table','DROP TABLE IF EXISTS `playlist_item`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(126,'create playlist table v2',replace('CREATE TABLE IF NOT EXISTS `playlist` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `name` TEXT NOT NULL\n, `interval` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(127,'create playlist item table v2',replace('CREATE TABLE IF NOT EXISTS `playlist_item` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `playlist_id` INTEGER NOT NULL\n, `type` TEXT NOT NULL\n, `value` TEXT NOT NULL\n, `title` TEXT NOT NULL\n, `order` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(128,'Update playlist table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(129,'Update playlist_item table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(130,'drop preferences table v2','DROP TABLE IF EXISTS `preferences`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(131,'drop preferences table v3','DROP TABLE IF EXISTS `preferences`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(132,'create preferences table v3',replace('CREATE TABLE IF NOT EXISTS `preferences` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `user_id` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `home_dashboard_id` INTEGER NOT NULL\n, `timezone` TEXT NOT NULL\n, `theme` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(133,'Update preferences table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(134,'Add column team_id in preferences','alter table `preferences` ADD COLUMN `team_id` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(135,'Update team_id column values in preferences','UPDATE preferences SET team_id=0 WHERE team_id IS NULL;',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(136,'create alert table v1',replace('CREATE TABLE IF NOT EXISTS `alert` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `version` INTEGER NOT NULL\n, `dashboard_id` INTEGER NOT NULL\n, `panel_id` INTEGER NOT NULL\n, `org_id` INTEGER NOT NULL\n, `name` TEXT NOT NULL\n, `message` TEXT NOT NULL\n, `state` TEXT NOT NULL\n, `settings` TEXT NOT NULL\n, `frequency` INTEGER NOT NULL\n, `handler` INTEGER NOT NULL\n, `severity` TEXT NOT NULL\n, `silenced` INTEGER NOT NULL\n, `execution_error` TEXT NOT NULL\n, `eval_data` TEXT NULL\n, `eval_date` DATETIME NULL\n, `new_state_date` DATETIME NOT NULL\n, `state_changes` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(137,'add index alert org_id & id ','CREATE INDEX `IDX_alert_org_id_id` ON `alert` (`org_id`,`id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(138,'add index alert state','CREATE INDEX `IDX_alert_state` ON `alert` (`state`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(139,'add index alert dashboard_id','CREATE INDEX `IDX_alert_dashboard_id` ON `alert` (`dashboard_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(140,'Create alert_rule_tag table v1',replace('CREATE TABLE IF NOT EXISTS `alert_rule_tag` (\n`alert_id` INTEGER NOT NULL\n, `tag_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(141,'Add unique index alert_rule_tag.alert_id_tag_id','CREATE UNIQUE INDEX `UQE_alert_rule_tag_alert_id_tag_id` ON `alert_rule_tag` (`alert_id`,`tag_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(142,'create alert_notification table v1',replace('CREATE TABLE IF NOT EXISTS `alert_notification` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `name` TEXT NOT NULL\n, `type` TEXT NOT NULL\n, `settings` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(143,'Add column is_default','alter table `alert_notification` ADD COLUMN `is_default` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(144,'Add column frequency','alter table `alert_notification` ADD COLUMN `frequency` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(145,'Add column send_reminder','alter table `alert_notification` ADD COLUMN `send_reminder` INTEGER NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(146,'Add column disable_resolve_message','alter table `alert_notification` ADD COLUMN `disable_resolve_message` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(147,'add index alert_notification org_id & name','CREATE UNIQUE INDEX `UQE_alert_notification_org_id_name` ON `alert_notification` (`org_id`,`name`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(148,'Update alert table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(149,'Update alert_notification table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(150,'create notification_journal table v1',replace('CREATE TABLE IF NOT EXISTS `alert_notification_journal` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `alert_id` INTEGER NOT NULL\n, `notifier_id` INTEGER NOT NULL\n, `sent_at` INTEGER NOT NULL\n, `success` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(151,'add index notification_journal org_id & alert_id & notifier_id','CREATE INDEX `IDX_alert_notification_journal_org_id_alert_id_notifier_id` ON `alert_notification_journal` (`org_id`,`alert_id`,`notifier_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(152,'drop alert_notification_journal','DROP TABLE IF EXISTS `alert_notification_journal`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(153,'create alert_notification_state table v1',replace('CREATE TABLE IF NOT EXISTS `alert_notification_state` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `alert_id` INTEGER NOT NULL\n, `notifier_id` INTEGER NOT NULL\n, `state` TEXT NOT NULL\n, `version` INTEGER NOT NULL\n, `updated_at` INTEGER NOT NULL\n, `alert_rule_state_updated_version` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(154,'add index alert_notification_state org_id & alert_id & notifier_id','CREATE UNIQUE INDEX `UQE_alert_notification_state_org_id_alert_id_notifier_id` ON `alert_notification_state` (`org_id`,`alert_id`,`notifier_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(155,'Add for to alert table','alter table `alert` ADD COLUMN `for` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(156,'Add column uid in alert_notification','alter table `alert_notification` ADD COLUMN `uid` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(157,'Update uid column values in alert_notification','UPDATE alert_notification SET uid=printf(''%09d'',id) WHERE uid IS NULL;',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(158,'Add unique index alert_notification_org_id_uid','CREATE UNIQUE INDEX `UQE_alert_notification_org_id_uid` ON `alert_notification` (`org_id`,`uid`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(159,'Remove unique index org_id_name','DROP INDEX `UQE_alert_notification_org_id_name`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(160,'Drop old annotation table v4','DROP TABLE IF EXISTS `annotation`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(161,'create annotation table v5',replace('CREATE TABLE IF NOT EXISTS `annotation` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `alert_id` INTEGER NULL\n, `user_id` INTEGER NULL\n, `dashboard_id` INTEGER NULL\n, `panel_id` INTEGER NULL\n, `category_id` INTEGER NULL\n, `type` TEXT NOT NULL\n, `title` TEXT NOT NULL\n, `text` TEXT NOT NULL\n, `metric` TEXT NULL\n, `prev_state` TEXT NOT NULL\n, `new_state` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `epoch` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(162,'add index annotation 0 v3','CREATE INDEX `IDX_annotation_org_id_alert_id` ON `annotation` (`org_id`,`alert_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(163,'add index annotation 1 v3','CREATE INDEX `IDX_annotation_org_id_type` ON `annotation` (`org_id`,`type`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(164,'add index annotation 2 v3','CREATE INDEX `IDX_annotation_org_id_category_id` ON `annotation` (`org_id`,`category_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(165,'add index annotation 3 v3','CREATE INDEX `IDX_annotation_org_id_dashboard_id_panel_id_epoch` ON `annotation` (`org_id`,`dashboard_id`,`panel_id`,`epoch`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(166,'add index annotation 4 v3','CREATE INDEX `IDX_annotation_org_id_epoch` ON `annotation` (`org_id`,`epoch`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(167,'Update annotation table charset','-- NOT REQUIRED',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(168,'Add column region_id to annotation table','alter table `annotation` ADD COLUMN `region_id` INTEGER NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(169,'Drop category_id index','DROP INDEX `IDX_annotation_org_id_category_id`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(170,'Add column tags to annotation table','alter table `annotation` ADD COLUMN `tags` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(171,'Create annotation_tag table v2',replace('CREATE TABLE IF NOT EXISTS `annotation_tag` (\n`annotation_id` INTEGER NOT NULL\n, `tag_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(172,'Add unique index annotation_tag.annotation_id_tag_id','CREATE UNIQUE INDEX `UQE_annotation_tag_annotation_id_tag_id` ON `annotation_tag` (`annotation_id`,`tag_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(173,'Update alert annotations and set TEXT to empty','UPDATE annotation SET TEXT = '''' WHERE alert_id > 0',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(174,'Add created time to annotation table','alter table `annotation` ADD COLUMN `created` INTEGER NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(175,'Add updated time to annotation table','alter table `annotation` ADD COLUMN `updated` INTEGER NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(176,'Add index for created in annotation table','CREATE INDEX `IDX_annotation_org_id_created` ON `annotation` (`org_id`,`created`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(177,'Add index for updated in annotation table','CREATE INDEX `IDX_annotation_org_id_updated` ON `annotation` (`org_id`,`updated`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(178,'Convert existing annotations from seconds to milliseconds','UPDATE annotation SET epoch = (epoch*1000) where epoch < 9999999999',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(179,'Add epoch_end column','alter table `annotation` ADD COLUMN `epoch_end` INTEGER NOT NULL DEFAULT 0 ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(180,'Add index for epoch_end','CREATE INDEX `IDX_annotation_org_id_epoch_epoch_end` ON `annotation` (`org_id`,`epoch`,`epoch_end`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(181,'Make epoch_end the same as epoch','UPDATE annotation SET epoch_end = epoch',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(182,'Move region to single row','code migration',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(183,'Remove index org_id_epoch from annotation table','DROP INDEX `IDX_annotation_org_id_epoch`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(184,'Remove index org_id_dashboard_id_panel_id_epoch from annotation table','DROP INDEX `IDX_annotation_org_id_dashboard_id_panel_id_epoch`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(185,'Add index for org_id_dashboard_id_epoch_end_epoch on annotation table','CREATE INDEX `IDX_annotation_org_id_dashboard_id_epoch_end_epoch` ON `annotation` (`org_id`,`dashboard_id`,`epoch_end`,`epoch`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(186,'Add index for org_id_epoch_end_epoch on annotation table','CREATE INDEX `IDX_annotation_org_id_epoch_end_epoch` ON `annotation` (`org_id`,`epoch_end`,`epoch`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(187,'Remove index org_id_epoch_epoch_end from annotation table','DROP INDEX `IDX_annotation_org_id_epoch_epoch_end`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(188,'create test_data table',replace('CREATE TABLE IF NOT EXISTS `test_data` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `metric1` TEXT NULL\n, `metric2` TEXT NULL\n, `value_big_int` INTEGER NULL\n, `value_double` REAL NULL\n, `value_float` REAL NULL\n, `value_int` INTEGER NULL\n, `time_epoch` INTEGER NOT NULL\n, `time_date_time` DATETIME NOT NULL\n, `time_time_stamp` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(189,'create dashboard_version table v1',replace('CREATE TABLE IF NOT EXISTS `dashboard_version` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `dashboard_id` INTEGER NOT NULL\n, `parent_version` INTEGER NOT NULL\n, `restored_from` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `created_by` INTEGER NOT NULL\n, `message` TEXT NOT NULL\n, `data` TEXT NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(190,'add index dashboard_version.dashboard_id','CREATE INDEX `IDX_dashboard_version_dashboard_id` ON `dashboard_version` (`dashboard_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(191,'add unique index dashboard_version.dashboard_id and dashboard_version.version','CREATE UNIQUE INDEX `UQE_dashboard_version_dashboard_id_version` ON `dashboard_version` (`dashboard_id`,`version`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(192,'Set dashboard version to 1 where 0','UPDATE dashboard SET version = 1 WHERE version = 0',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(193,'save existing dashboard data in dashboard_version table v1',replace('INSERT INTO dashboard_version\n(\n	dashboard_id,\n	version,\n	parent_version,\n	restored_from,\n	created,\n	created_by,\n	message,\n	data\n)\nSELECT\n	dashboard.id,\n	dashboard.version,\n	dashboard.version,\n	dashboard.version,\n	dashboard.updated,\n	COALESCE(dashboard.updated_by, -1),\n	'''',\n	dashboard.data\nFROM dashboard;','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(194,'alter dashboard_version.data to mediumtext v1','SELECT 0;',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(195,'create team table',replace('CREATE TABLE IF NOT EXISTS `team` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `name` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(196,'add index team.org_id','CREATE INDEX `IDX_team_org_id` ON `team` (`org_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(197,'add unique index team_org_id_name','CREATE UNIQUE INDEX `UQE_team_org_id_name` ON `team` (`org_id`,`name`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(198,'create team member table',replace('CREATE TABLE IF NOT EXISTS `team_member` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `team_id` INTEGER NOT NULL\n, `user_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(199,'add index team_member.org_id','CREATE INDEX `IDX_team_member_org_id` ON `team_member` (`org_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(200,'add unique index team_member_org_id_team_id_user_id','CREATE UNIQUE INDEX `UQE_team_member_org_id_team_id_user_id` ON `team_member` (`org_id`,`team_id`,`user_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(201,'Add column email to team table','alter table `team` ADD COLUMN `email` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(202,'Add column external to team_member table','alter table `team_member` ADD COLUMN `external` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(203,'Add column permission to team_member table','alter table `team_member` ADD COLUMN `permission` INTEGER NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(204,'create dashboard acl table',replace('CREATE TABLE IF NOT EXISTS `dashboard_acl` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `dashboard_id` INTEGER NOT NULL\n, `user_id` INTEGER NULL\n, `team_id` INTEGER NULL\n, `permission` INTEGER NOT NULL DEFAULT 4\n, `role` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(205,'add index dashboard_acl_dashboard_id','CREATE INDEX `IDX_dashboard_acl_dashboard_id` ON `dashboard_acl` (`dashboard_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(206,'add unique index dashboard_acl_dashboard_id_user_id','CREATE UNIQUE INDEX `UQE_dashboard_acl_dashboard_id_user_id` ON `dashboard_acl` (`dashboard_id`,`user_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(207,'add unique index dashboard_acl_dashboard_id_team_id','CREATE UNIQUE INDEX `UQE_dashboard_acl_dashboard_id_team_id` ON `dashboard_acl` (`dashboard_id`,`team_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(208,'save default acl rules in dashboard_acl table',replace('\nINSERT INTO dashboard_acl\n	(\n		org_id,\n		dashboard_id,\n		permission,\n		role,\n		created,\n		updated\n	)\n	VALUES\n		(-1,-1, 1,''Viewer'',''2017-06-20'',''2017-06-20''),\n		(-1,-1, 2,''Editor'',''2017-06-20'',''2017-06-20'')\n	','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(209,'create tag table',replace('CREATE TABLE IF NOT EXISTS `tag` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `key` TEXT NOT NULL\n, `value` TEXT NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(210,'add index tag.key_value','CREATE UNIQUE INDEX `UQE_tag_key_value` ON `tag` (`key`,`value`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(211,'create login attempt table',replace('CREATE TABLE IF NOT EXISTS `login_attempt` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `username` TEXT NOT NULL\n, `ip_address` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(212,'add index login_attempt.username','CREATE INDEX `IDX_login_attempt_username` ON `login_attempt` (`username`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(213,'drop index IDX_login_attempt_username - v1','DROP INDEX `IDX_login_attempt_username`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(214,'Rename table login_attempt to login_attempt_tmp_qwerty - v1','ALTER TABLE `login_attempt` RENAME TO `login_attempt_tmp_qwerty`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(215,'create login_attempt v2',replace('CREATE TABLE IF NOT EXISTS `login_attempt` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `username` TEXT NOT NULL\n, `ip_address` TEXT NOT NULL\n, `created` INTEGER NOT NULL DEFAULT 0\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(216,'create index IDX_login_attempt_username - v2','CREATE INDEX `IDX_login_attempt_username` ON `login_attempt` (`username`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(217,'copy login_attempt v1 to v2',replace('INSERT INTO `login_attempt` (`id`\n, `username`\n, `ip_address`) SELECT `id`\n, `username`\n, `ip_address` FROM `login_attempt_tmp_qwerty`','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(218,'drop login_attempt_tmp_qwerty','DROP TABLE IF EXISTS `login_attempt_tmp_qwerty`',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(219,'create user auth table',replace('CREATE TABLE IF NOT EXISTS `user_auth` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `user_id` INTEGER NOT NULL\n, `auth_module` TEXT NOT NULL\n, `auth_id` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(220,'create index IDX_user_auth_auth_module_auth_id - v1','CREATE INDEX `IDX_user_auth_auth_module_auth_id` ON `user_auth` (`auth_module`,`auth_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(221,'alter user_auth.auth_id to length 190','SELECT 0;',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(222,'Add OAuth access token to user_auth','alter table `user_auth` ADD COLUMN `o_auth_access_token` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(223,'Add OAuth refresh token to user_auth','alter table `user_auth` ADD COLUMN `o_auth_refresh_token` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(224,'Add OAuth token type to user_auth','alter table `user_auth` ADD COLUMN `o_auth_token_type` TEXT NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(225,'Add OAuth expiry to user_auth','alter table `user_auth` ADD COLUMN `o_auth_expiry` DATETIME NULL ',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(226,'Add index to user_id column in user_auth','CREATE INDEX `IDX_user_auth_user_id` ON `user_auth` (`user_id`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(227,'create server_lock table',replace('CREATE TABLE IF NOT EXISTS `server_lock` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `operation_uid` TEXT NOT NULL\n, `version` INTEGER NOT NULL\n, `last_execution` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(228,'add index server_lock.operation_uid','CREATE UNIQUE INDEX `UQE_server_lock_operation_uid` ON `server_lock` (`operation_uid`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(229,'create user auth token table',replace('CREATE TABLE IF NOT EXISTS `user_auth_token` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `user_id` INTEGER NOT NULL\n, `auth_token` TEXT NOT NULL\n, `prev_auth_token` TEXT NOT NULL\n, `user_agent` TEXT NOT NULL\n, `client_ip` TEXT NOT NULL\n, `auth_token_seen` INTEGER NOT NULL\n, `seen_at` INTEGER NULL\n, `rotated_at` INTEGER NOT NULL\n, `created_at` INTEGER NOT NULL\n, `updated_at` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(230,'add unique index user_auth_token.auth_token','CREATE UNIQUE INDEX `UQE_user_auth_token_auth_token` ON `user_auth_token` (`auth_token`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(231,'add unique index user_auth_token.prev_auth_token','CREATE UNIQUE INDEX `UQE_user_auth_token_prev_auth_token` ON `user_auth_token` (`prev_auth_token`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(232,'create cache_data table',replace('CREATE TABLE IF NOT EXISTS `cache_data` (\n`cache_key` TEXT PRIMARY KEY NOT NULL\n, `data` BLOB NOT NULL\n, `expires` INTEGER NOT NULL\n, `created_at` INTEGER NOT NULL\n);','\n',char(10)),1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(233,'add unique index cache_data.cache_key','CREATE UNIQUE INDEX `UQE_cache_data_cache_key` ON `cache_data` (`cache_key`);',1,'','2020-02-18 16:17:55');
INSERT INTO migration_log VALUES(234,'Add index user.login/user.email','CREATE INDEX `IDX_user_login_email` ON `user` (`login`,`email`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(235,'Add is_service_account column to user','alter table `user` ADD COLUMN `is_service_account` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(236,'Update is_service_account column to nullable',replace('ALTER TABLE user ADD COLUMN tmp_service_account BOOLEAN DEFAULT 0;\nUPDATE user SET tmp_service_account = is_service_account;\nALTER TABLE user DROP COLUMN is_service_account;\nALTER TABLE user RENAME COLUMN tmp_service_account TO is_service_account;','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(237,'drop index IDX_temp_user_email - v1','DROP INDEX `IDX_temp_user_email`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(238,'drop index IDX_temp_user_org_id - v1','DROP INDEX `IDX_temp_user_org_id`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(239,'drop index IDX_temp_user_code - v1','DROP INDEX `IDX_temp_user_code`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(240,'drop index IDX_temp_user_status - v1','DROP INDEX `IDX_temp_user_status`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(241,'Rename table temp_user to temp_user_tmp_qwerty - v1','ALTER TABLE `temp_user` RENAME TO `temp_user_tmp_qwerty`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(242,'create temp_user v2',replace('CREATE TABLE IF NOT EXISTS `temp_user` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `email` TEXT NOT NULL\n, `name` TEXT NULL\n, `role` TEXT NULL\n, `code` TEXT NOT NULL\n, `status` TEXT NOT NULL\n, `invited_by_user_id` INTEGER NULL\n, `email_sent` INTEGER NOT NULL\n, `email_sent_on` DATETIME NULL\n, `remote_addr` TEXT NULL\n, `created` INTEGER NOT NULL DEFAULT 0\n, `updated` INTEGER NOT NULL DEFAULT 0\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(243,'create index IDX_temp_user_email - v2','CREATE INDEX `IDX_temp_user_email` ON `temp_user` (`email`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(244,'create index IDX_temp_user_org_id - v2','CREATE INDEX `IDX_temp_user_org_id` ON `temp_user` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(245,'create index IDX_temp_user_code - v2','CREATE INDEX `IDX_temp_user_code` ON `temp_user` (`code`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(246,'create index IDX_temp_user_status - v2','CREATE INDEX `IDX_temp_user_status` ON `temp_user` (`status`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(247,'copy temp_user v1 to v2',replace('INSERT INTO `temp_user` (`id`\n, `name`\n, `code`\n, `email_sent_on`\n, `remote_addr`\n, `org_id`\n, `version`\n, `email`\n, `role`\n, `status`\n, `invited_by_user_id`\n, `email_sent`) SELECT `id`\n, `name`\n, `code`\n, `email_sent_on`\n, `remote_addr`\n, `org_id`\n, `version`\n, `email`\n, `role`\n, `status`\n, `invited_by_user_id`\n, `email_sent` FROM `temp_user_tmp_qwerty`','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(248,'drop temp_user_tmp_qwerty','DROP TABLE IF EXISTS `temp_user_tmp_qwerty`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(249,'Set created for temp users that will otherwise prematurely expire','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(250,'create index IDX_org_user_user_id - v1','CREATE INDEX `IDX_org_user_user_id` ON `org_user` (`user_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(251,'Add index for dashboard_title','CREATE INDEX `IDX_dashboard_title` ON `dashboard` (`title`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(252,'delete tags for deleted dashboards','DELETE FROM dashboard_tag WHERE dashboard_id NOT IN (SELECT id FROM dashboard)',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(253,'delete stars for deleted dashboards','DELETE FROM star WHERE dashboard_id NOT IN (SELECT id FROM dashboard)',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(254,'Add index for dashboard_is_folder','CREATE INDEX `IDX_dashboard_is_folder` ON `dashboard` (`is_folder`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(255,'Add isPublic for dashboard','alter table `dashboard` ADD COLUMN `is_public` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(256,'Add uid column','alter table `data_source` ADD COLUMN `uid` TEXT NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(257,'Update uid value','UPDATE data_source SET uid=printf(''%09d'',id);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(258,'Add unique index datasource_org_id_uid','CREATE UNIQUE INDEX `UQE_data_source_org_id_uid` ON `data_source` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(259,'add unique index datasource_org_id_is_default','CREATE INDEX `IDX_data_source_org_id_is_default` ON `data_source` (`org_id`,`is_default`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(260,'Add service account foreign key','alter table `api_key` ADD COLUMN `service_account_id` INTEGER NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(261,'set service account foreign key to nil if 0','UPDATE api_key SET service_account_id = NULL WHERE service_account_id = 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(262,'Add last_used_at to api_key table','alter table `api_key` ADD COLUMN `last_used_at` DATETIME NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(263,'Add is_revoked column to api_key table','alter table `api_key` ADD COLUMN `is_revoked` INTEGER NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(264,'Add encrypted dashboard json column','alter table `dashboard_snapshot` ADD COLUMN `dashboard_encrypted` BLOB NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(265,'Change dashboard_encrypted column to MEDIUMBLOB','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(266,'Add column week_start in preferences','alter table `preferences` ADD COLUMN `week_start` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(267,'Add column preferences.json_data','alter table `preferences` ADD COLUMN `json_data` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(268,'alter preferences.json_data to mediumtext v1','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(269,'Add preferences index org_id','CREATE INDEX `IDX_preferences_org_id` ON `preferences` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(270,'Add preferences index user_id','CREATE INDEX `IDX_preferences_user_id` ON `preferences` (`user_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(271,'drop index UQE_alert_rule_tag_alert_id_tag_id - v1','DROP INDEX `UQE_alert_rule_tag_alert_id_tag_id`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(272,'Rename table alert_rule_tag to alert_rule_tag_v1 - v1','ALTER TABLE `alert_rule_tag` RENAME TO `alert_rule_tag_v1`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(273,'Create alert_rule_tag table v2',replace('CREATE TABLE IF NOT EXISTS `alert_rule_tag` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `alert_id` INTEGER NOT NULL\n, `tag_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(274,'create index UQE_alert_rule_tag_alert_id_tag_id - Add unique index alert_rule_tag.alert_id_tag_id V2','CREATE UNIQUE INDEX `UQE_alert_rule_tag_alert_id_tag_id` ON `alert_rule_tag` (`alert_id`,`tag_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(275,'copy alert_rule_tag v1 to v2',replace('INSERT INTO `alert_rule_tag` (`alert_id`\n, `tag_id`) SELECT `alert_id`\n, `tag_id` FROM `alert_rule_tag_v1`','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(276,'drop table alert_rule_tag_v1','DROP TABLE IF EXISTS `alert_rule_tag_v1`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(277,'Add column secure_settings in alert_notification','alter table `alert_notification` ADD COLUMN `secure_settings` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(278,'alter alert.settings to mediumtext','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(279,'Add non-unique index alert_notification_state_alert_id','CREATE INDEX `IDX_alert_notification_state_alert_id` ON `alert_notification_state` (`alert_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(280,'Add non-unique index alert_rule_tag_alert_id','CREATE INDEX `IDX_alert_rule_tag_alert_id` ON `alert_rule_tag` (`alert_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(281,'drop index UQE_annotation_tag_annotation_id_tag_id - v2','DROP INDEX `UQE_annotation_tag_annotation_id_tag_id`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(282,'Rename table annotation_tag to annotation_tag_v2 - v2','ALTER TABLE `annotation_tag` RENAME TO `annotation_tag_v2`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(283,'Create annotation_tag table v3',replace('CREATE TABLE IF NOT EXISTS `annotation_tag` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `annotation_id` INTEGER NOT NULL\n, `tag_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(284,'create index UQE_annotation_tag_annotation_id_tag_id - Add unique index annotation_tag.annotation_id_tag_id V3','CREATE UNIQUE INDEX `UQE_annotation_tag_annotation_id_tag_id` ON `annotation_tag` (`annotation_id`,`tag_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(285,'copy annotation_tag v2 to v3',replace('INSERT INTO `annotation_tag` (`annotation_id`\n, `tag_id`) SELECT `annotation_id`\n, `tag_id` FROM `annotation_tag_v2`','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(286,'drop table annotation_tag_v2','DROP TABLE IF EXISTS `annotation_tag_v2`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(287,'Add index for alert_id on annotation table','CREATE INDEX `IDX_annotation_alert_id` ON `annotation` (`alert_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(288,'Increase tags column to length 4096','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(289,'add index team_member.team_id','CREATE INDEX `IDX_team_member_team_id` ON `team_member` (`team_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(290,'add index dashboard_acl_user_id','CREATE INDEX `IDX_dashboard_acl_user_id` ON `dashboard_acl` (`user_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(291,'add index dashboard_acl_team_id','CREATE INDEX `IDX_dashboard_acl_team_id` ON `dashboard_acl` (`team_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(292,'add index dashboard_acl_org_id_role','CREATE INDEX `IDX_dashboard_acl_org_id_role` ON `dashboard_acl` (`org_id`,`role`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(293,'add index dashboard_permission','CREATE INDEX `IDX_dashboard_acl_permission` ON `dashboard_acl` (`permission`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(294,'delete acl rules for deleted dashboards and folders','DELETE FROM dashboard_acl WHERE dashboard_id NOT IN (SELECT id FROM dashboard) AND dashboard_id != -1',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(295,'Add OAuth ID token to user_auth','alter table `user_auth` ADD COLUMN `o_auth_id_token` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(296,'add index user_auth_token.user_id','CREATE INDEX `IDX_user_auth_token_user_id` ON `user_auth_token` (`user_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(297,'Add revoked_at to the user auth token','alter table `user_auth_token` ADD COLUMN `revoked_at` INTEGER NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(298,'create short_url table v1',replace('CREATE TABLE IF NOT EXISTS `short_url` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `uid` TEXT NOT NULL\n, `path` TEXT NOT NULL\n, `created_by` INTEGER NOT NULL\n, `created_at` INTEGER NOT NULL\n, `last_seen_at` INTEGER NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(299,'add index short_url.org_id-uid','CREATE UNIQUE INDEX `UQE_short_url_org_id_uid` ON `short_url` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(300,'alter table short_url alter column created_by type to bigint','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(301,'delete alert_definition table','DROP TABLE IF EXISTS `alert_definition`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(302,'recreate alert_definition table',replace('CREATE TABLE IF NOT EXISTS `alert_definition` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `title` TEXT NOT NULL\n, `condition` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `updated` DATETIME NOT NULL\n, `interval_seconds` INTEGER NOT NULL DEFAULT 60\n, `version` INTEGER NOT NULL DEFAULT 0\n, `uid` TEXT NOT NULL DEFAULT 0\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(303,'add index in alert_definition on org_id and title columns','CREATE INDEX `IDX_alert_definition_org_id_title` ON `alert_definition` (`org_id`,`title`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(304,'add index in alert_definition on org_id and uid columns','CREATE INDEX `IDX_alert_definition_org_id_uid` ON `alert_definition` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(305,'alter alert_definition table data column to mediumtext in mysql','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(306,'drop index in alert_definition on org_id and title columns','DROP INDEX `IDX_alert_definition_org_id_title`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(307,'drop index in alert_definition on org_id and uid columns','DROP INDEX `IDX_alert_definition_org_id_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(308,'add unique index in alert_definition on org_id and title columns','CREATE UNIQUE INDEX `UQE_alert_definition_org_id_title` ON `alert_definition` (`org_id`,`title`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(309,'add unique index in alert_definition on org_id and uid columns','CREATE UNIQUE INDEX `UQE_alert_definition_org_id_uid` ON `alert_definition` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(310,'Add column paused in alert_definition','alter table `alert_definition` ADD COLUMN `paused` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(311,'drop alert_definition table','DROP TABLE IF EXISTS `alert_definition`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(312,'delete alert_definition_version table','DROP TABLE IF EXISTS `alert_definition_version`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(313,'recreate alert_definition_version table',replace('CREATE TABLE IF NOT EXISTS `alert_definition_version` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `alert_definition_id` INTEGER NOT NULL\n, `alert_definition_uid` TEXT NOT NULL DEFAULT 0\n, `parent_version` INTEGER NOT NULL\n, `restored_from` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `title` TEXT NOT NULL\n, `condition` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `interval_seconds` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(314,'add index in alert_definition_version table on alert_definition_id and version columns','CREATE UNIQUE INDEX `UQE_alert_definition_version_alert_definition_id_version` ON `alert_definition_version` (`alert_definition_id`,`version`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(315,'add index in alert_definition_version table on alert_definition_uid and version columns','CREATE UNIQUE INDEX `UQE_alert_definition_version_alert_definition_uid_version` ON `alert_definition_version` (`alert_definition_uid`,`version`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(316,'alter alert_definition_version table data column to mediumtext in mysql','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(317,'drop alert_definition_version table','DROP TABLE IF EXISTS `alert_definition_version`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(318,'create alert_instance table',replace('CREATE TABLE IF NOT EXISTS `alert_instance` (\n`def_org_id` INTEGER NOT NULL\n, `def_uid` TEXT NOT NULL DEFAULT 0\n, `labels` TEXT NOT NULL\n, `labels_hash` TEXT NOT NULL\n, `current_state` TEXT NOT NULL\n, `current_state_since` INTEGER NOT NULL\n, `last_eval_time` INTEGER NOT NULL\n, PRIMARY KEY ( `def_org_id`,`def_uid`,`labels_hash` ));','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(319,'add index in alert_instance table on def_org_id, def_uid and current_state columns','CREATE INDEX `IDX_alert_instance_def_org_id_def_uid_current_state` ON `alert_instance` (`def_org_id`,`def_uid`,`current_state`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(320,'add index in alert_instance table on def_org_id, current_state columns','CREATE INDEX `IDX_alert_instance_def_org_id_current_state` ON `alert_instance` (`def_org_id`,`current_state`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(321,'add column current_state_end to alert_instance','alter table `alert_instance` ADD COLUMN `current_state_end` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(322,'remove index def_org_id, def_uid, current_state on alert_instance','DROP INDEX `IDX_alert_instance_def_org_id_def_uid_current_state`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(323,'remove index def_org_id, current_state on alert_instance','DROP INDEX `IDX_alert_instance_def_org_id_current_state`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(324,'rename def_org_id to rule_org_id in alert_instance','ALTER TABLE alert_instance RENAME COLUMN def_org_id TO rule_org_id;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(325,'rename def_uid to rule_uid in alert_instance','ALTER TABLE alert_instance RENAME COLUMN def_uid TO rule_uid;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(326,'add index rule_org_id, rule_uid, current_state on alert_instance','CREATE INDEX `IDX_alert_instance_rule_org_id_rule_uid_current_state` ON `alert_instance` (`rule_org_id`,`rule_uid`,`current_state`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(327,'add index rule_org_id, current_state on alert_instance','CREATE INDEX `IDX_alert_instance_rule_org_id_current_state` ON `alert_instance` (`rule_org_id`,`current_state`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(328,'add current_reason column related to current_state','alter table `alert_instance` ADD COLUMN `current_reason` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(329,'create alert_rule table',replace('CREATE TABLE IF NOT EXISTS `alert_rule` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `title` TEXT NOT NULL\n, `condition` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `updated` DATETIME NOT NULL\n, `interval_seconds` INTEGER NOT NULL DEFAULT 60\n, `version` INTEGER NOT NULL DEFAULT 0\n, `uid` TEXT NOT NULL DEFAULT 0\n, `namespace_uid` TEXT NOT NULL\n, `rule_group` TEXT NOT NULL\n, `no_data_state` TEXT NOT NULL DEFAULT ''NoData''\n, `exec_err_state` TEXT NOT NULL DEFAULT ''Alerting''\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(330,'add index in alert_rule on org_id and title columns','CREATE UNIQUE INDEX `UQE_alert_rule_org_id_title` ON `alert_rule` (`org_id`,`title`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(331,'add index in alert_rule on org_id and uid columns','CREATE UNIQUE INDEX `UQE_alert_rule_org_id_uid` ON `alert_rule` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(332,'add index in alert_rule on org_id, namespace_uid, group_uid columns','CREATE INDEX `IDX_alert_rule_org_id_namespace_uid_rule_group` ON `alert_rule` (`org_id`,`namespace_uid`,`rule_group`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(333,'alter alert_rule table data column to mediumtext in mysql','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(334,'add column for to alert_rule','alter table `alert_rule` ADD COLUMN `for` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(335,'add column annotations to alert_rule','alter table `alert_rule` ADD COLUMN `annotations` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(336,'add column labels to alert_rule','alter table `alert_rule` ADD COLUMN `labels` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(337,'remove unique index from alert_rule on org_id, title columns','DROP INDEX `UQE_alert_rule_org_id_title`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(338,'add index in alert_rule on org_id, namespase_uid and title columns','CREATE UNIQUE INDEX `UQE_alert_rule_org_id_namespace_uid_title` ON `alert_rule` (`org_id`,`namespace_uid`,`title`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(339,'add dashboard_uid column to alert_rule','alter table `alert_rule` ADD COLUMN `dashboard_uid` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(340,'add panel_id column to alert_rule','alter table `alert_rule` ADD COLUMN `panel_id` INTEGER NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(341,'add index in alert_rule on org_id, dashboard_uid and panel_id columns','CREATE INDEX `IDX_alert_rule_org_id_dashboard_uid_panel_id` ON `alert_rule` (`org_id`,`dashboard_uid`,`panel_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(342,'add rule_group_idx column to alert_rule','alter table `alert_rule` ADD COLUMN `rule_group_idx` INTEGER NOT NULL DEFAULT 1 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(343,'create alert_rule_version table',replace('CREATE TABLE IF NOT EXISTS `alert_rule_version` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `rule_org_id` INTEGER NOT NULL\n, `rule_uid` TEXT NOT NULL DEFAULT 0\n, `rule_namespace_uid` TEXT NOT NULL\n, `rule_group` TEXT NOT NULL\n, `parent_version` INTEGER NOT NULL\n, `restored_from` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `title` TEXT NOT NULL\n, `condition` TEXT NOT NULL\n, `data` TEXT NOT NULL\n, `interval_seconds` INTEGER NOT NULL\n, `no_data_state` TEXT NOT NULL DEFAULT ''NoData''\n, `exec_err_state` TEXT NOT NULL DEFAULT ''Alerting''\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(344,'add index in alert_rule_version table on rule_org_id, rule_uid and version columns','CREATE UNIQUE INDEX `UQE_alert_rule_version_rule_org_id_rule_uid_version` ON `alert_rule_version` (`rule_org_id`,`rule_uid`,`version`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(345,'add index in alert_rule_version table on rule_org_id, rule_namespace_uid and rule_group columns','CREATE INDEX `IDX_alert_rule_version_rule_org_id_rule_namespace_uid_rule_group` ON `alert_rule_version` (`rule_org_id`,`rule_namespace_uid`,`rule_group`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(346,'alter alert_rule_version table data column to mediumtext in mysql','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(347,'add column for to alert_rule_version','alter table `alert_rule_version` ADD COLUMN `for` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(348,'add column annotations to alert_rule_version','alter table `alert_rule_version` ADD COLUMN `annotations` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(349,'add column labels to alert_rule_version','alter table `alert_rule_version` ADD COLUMN `labels` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(350,'add rule_group_idx column to alert_rule_version','alter table `alert_rule_version` ADD COLUMN `rule_group_idx` INTEGER NOT NULL DEFAULT 1 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(351,'create_alert_configuration_table',replace('CREATE TABLE IF NOT EXISTS `alert_configuration` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `alertmanager_configuration` TEXT NOT NULL\n, `configuration_version` TEXT NOT NULL\n, `created_at` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(352,'Add column default in alert_configuration','alter table `alert_configuration` ADD COLUMN `default` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(353,'alert alert_configuration alertmanager_configuration column from TEXT to MEDIUMTEXT if mysql','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(354,'add column org_id in alert_configuration','alter table `alert_configuration` ADD COLUMN `org_id` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(355,'add index in alert_configuration table on org_id column','CREATE INDEX `IDX_alert_configuration_org_id` ON `alert_configuration` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(356,'add configuration_hash column to alert_configuration','alter table `alert_configuration` ADD COLUMN `configuration_hash` TEXT NOT NULL DEFAULT ''not-yet-calculated'' ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(357,'create_ngalert_configuration_table',replace('CREATE TABLE IF NOT EXISTS `ngalert_configuration` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `alertmanagers` TEXT NULL\n, `created_at` INTEGER NOT NULL\n, `updated_at` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(358,'add index in ngalert_configuration on org_id column','CREATE UNIQUE INDEX `UQE_ngalert_configuration_org_id` ON `ngalert_configuration` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(359,'add column send_alerts_to in ngalert_configuration','alter table `ngalert_configuration` ADD COLUMN `send_alerts_to` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(360,'create provenance_type table',replace('CREATE TABLE IF NOT EXISTS `provenance_type` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `record_key` TEXT NOT NULL\n, `record_type` TEXT NOT NULL\n, `provenance` TEXT NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(361,'add index to uniquify (record_key, record_type, org_id) columns','CREATE UNIQUE INDEX `UQE_provenance_type_record_type_record_key_org_id` ON `provenance_type` (`record_type`,`record_key`,`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(362,'create alert_image table',replace('CREATE TABLE IF NOT EXISTS `alert_image` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `token` TEXT NOT NULL\n, `path` TEXT NOT NULL\n, `url` TEXT NOT NULL\n, `created_at` DATETIME NOT NULL\n, `expires_at` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(363,'add unique index on token to alert_image table','CREATE UNIQUE INDEX `UQE_alert_image_token` ON `alert_image` (`token`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(364,'support longer URLs in alert_image table','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(365,'move dashboard alerts to unified alerting','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(366,'create library_element table v1',replace('CREATE TABLE IF NOT EXISTS `library_element` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `folder_id` INTEGER NOT NULL\n, `uid` TEXT NOT NULL\n, `name` TEXT NOT NULL\n, `kind` INTEGER NOT NULL\n, `type` TEXT NOT NULL\n, `description` TEXT NOT NULL\n, `model` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `created_by` INTEGER NOT NULL\n, `updated` DATETIME NOT NULL\n, `updated_by` INTEGER NOT NULL\n, `version` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(367,'add index library_element org_id-folder_id-name-kind','CREATE UNIQUE INDEX `UQE_library_element_org_id_folder_id_name_kind` ON `library_element` (`org_id`,`folder_id`,`name`,`kind`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(368,'create library_element_connection table v1',replace('CREATE TABLE IF NOT EXISTS `library_element_connection` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `element_id` INTEGER NOT NULL\n, `kind` INTEGER NOT NULL\n, `connection_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `created_by` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(369,'add index library_element_connection element_id-kind-connection_id','CREATE UNIQUE INDEX `UQE_library_element_connection_element_id_kind_connection_id` ON `library_element_connection` (`element_id`,`kind`,`connection_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(370,'add unique index library_element org_id_uid','CREATE UNIQUE INDEX `UQE_library_element_org_id_uid` ON `library_element` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(371,'increase max description length to 2048','-- NOT REQUIRED',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(372,'clone move dashboard alerts to unified alerting','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(373,'create data_keys table',replace('CREATE TABLE IF NOT EXISTS `data_keys` (\n`name` TEXT PRIMARY KEY NOT NULL\n, `active` INTEGER NOT NULL\n, `scope` TEXT NOT NULL\n, `provider` TEXT NOT NULL\n, `encrypted_data` BLOB NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(374,'create secrets table',replace('CREATE TABLE IF NOT EXISTS `secrets` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `namespace` TEXT NOT NULL\n, `type` TEXT NOT NULL\n, `value` TEXT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(375,'rename data_keys name column to id','ALTER TABLE `data_keys` RENAME COLUMN `name` TO `id`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(376,'add name column into data_keys','alter table `data_keys` ADD COLUMN `name` TEXT NOT NULL DEFAULT '''' ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(377,'copy data_keys id column values into name','UPDATE data_keys SET name = id',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(378,'rename data_keys name column to label','ALTER TABLE `data_keys` RENAME COLUMN `name` TO `label`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(379,'rename data_keys id column back to name','ALTER TABLE `data_keys` RENAME COLUMN `id` TO `name`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(380,'create kv_store table v1',replace('CREATE TABLE IF NOT EXISTS `kv_store` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `namespace` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `value` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(381,'add index kv_store.org_id-namespace-key','CREATE UNIQUE INDEX `UQE_kv_store_org_id_namespace_key` ON `kv_store` (`org_id`,`namespace`,`key`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(382,'update dashboard_uid and panel_id from existing annotations','set dashboard_uid and panel_id migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(383,'create permission table',replace('CREATE TABLE IF NOT EXISTS `permission` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `role_id` INTEGER NOT NULL\n, `action` TEXT NOT NULL\n, `scope` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(384,'add unique index permission.role_id','CREATE INDEX `IDX_permission_role_id` ON `permission` (`role_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(385,'add unique index role_id_action_scope','CREATE UNIQUE INDEX `UQE_permission_role_id_action_scope` ON `permission` (`role_id`,`action`,`scope`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(386,'create role table',replace('CREATE TABLE IF NOT EXISTS `role` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `name` TEXT NOT NULL\n, `description` TEXT NULL\n, `version` INTEGER NOT NULL\n, `org_id` INTEGER NOT NULL\n, `uid` TEXT NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(387,'add column display_name','alter table `role` ADD COLUMN `display_name` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(388,'add column group_name','alter table `role` ADD COLUMN `group_name` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(389,'add index role.org_id','CREATE INDEX `IDX_role_org_id` ON `role` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(390,'add unique index role_org_id_name','CREATE UNIQUE INDEX `UQE_role_org_id_name` ON `role` (`org_id`,`name`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(391,'add index role_org_id_uid','CREATE UNIQUE INDEX `UQE_role_org_id_uid` ON `role` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(392,'create team role table',replace('CREATE TABLE IF NOT EXISTS `team_role` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `team_id` INTEGER NOT NULL\n, `role_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(393,'add index team_role.org_id','CREATE INDEX `IDX_team_role_org_id` ON `team_role` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(394,'add unique index team_role_org_id_team_id_role_id','CREATE UNIQUE INDEX `UQE_team_role_org_id_team_id_role_id` ON `team_role` (`org_id`,`team_id`,`role_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(395,'add index team_role.team_id','CREATE INDEX `IDX_team_role_team_id` ON `team_role` (`team_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(396,'create user role table',replace('CREATE TABLE IF NOT EXISTS `user_role` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `user_id` INTEGER NOT NULL\n, `role_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(397,'add index user_role.org_id','CREATE INDEX `IDX_user_role_org_id` ON `user_role` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(398,'add unique index user_role_org_id_user_id_role_id','CREATE UNIQUE INDEX `UQE_user_role_org_id_user_id_role_id` ON `user_role` (`org_id`,`user_id`,`role_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(399,'add index user_role.user_id','CREATE INDEX `IDX_user_role_user_id` ON `user_role` (`user_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(400,'create builtin role table',replace('CREATE TABLE IF NOT EXISTS `builtin_role` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `role` TEXT NOT NULL\n, `role_id` INTEGER NOT NULL\n, `created` DATETIME NOT NULL\n, `updated` DATETIME NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(401,'add index builtin_role.role_id','CREATE INDEX `IDX_builtin_role_role_id` ON `builtin_role` (`role_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(402,'add index builtin_role.name','CREATE INDEX `IDX_builtin_role_role` ON `builtin_role` (`role`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(403,'Add column org_id to builtin_role table','alter table `builtin_role` ADD COLUMN `org_id` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(404,'add index builtin_role.org_id','CREATE INDEX `IDX_builtin_role_org_id` ON `builtin_role` (`org_id`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(405,'add unique index builtin_role_org_id_role_id_role','CREATE UNIQUE INDEX `UQE_builtin_role_org_id_role_id_role` ON `builtin_role` (`org_id`,`role_id`,`role`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(406,'Remove unique index role_org_id_uid','DROP INDEX `UQE_role_org_id_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(407,'add unique index role.uid','CREATE UNIQUE INDEX `UQE_role_uid` ON `role` (`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(408,'create seed assignment table',replace('CREATE TABLE IF NOT EXISTS `seed_assignment` (\n`builtin_role` TEXT NOT NULL\n, `role_name` TEXT NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(409,'add unique index builtin_role_role_name','CREATE UNIQUE INDEX `UQE_seed_assignment_builtin_role_role_name` ON `seed_assignment` (`builtin_role`,`role_name`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(410,'add column hidden to role table','alter table `role` ADD COLUMN `hidden` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(411,'create query_history table v1',replace('CREATE TABLE IF NOT EXISTS `query_history` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `uid` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `datasource_uid` TEXT NOT NULL\n, `created_by` INTEGER NOT NULL\n, `created_at` INTEGER NOT NULL\n, `comment` TEXT NOT NULL\n, `queries` TEXT NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(412,'add index query_history.org_id-created_by-datasource_uid','CREATE INDEX `IDX_query_history_org_id_created_by_datasource_uid` ON `query_history` (`org_id`,`created_by`,`datasource_uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(413,'alter table query_history alter column created_by type to bigint','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(414,'teams permissions migration','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(415,'dashboard permissions','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(416,'dashboard permissions uid scopes','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(417,'drop managed folder create actions','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(418,'alerting notification permissions','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(419,'create query_history_star table v1',replace('CREATE TABLE IF NOT EXISTS `query_history_star` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `query_uid` TEXT NOT NULL\n, `user_id` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(420,'add index query_history.user_id-query_uid','CREATE UNIQUE INDEX `UQE_query_history_star_user_id_query_uid` ON `query_history_star` (`user_id`,`query_uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(421,'add column org_id in query_history_star','alter table `query_history_star` ADD COLUMN `org_id` INTEGER NOT NULL DEFAULT 1 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(422,'alter table query_history_star_mig column user_id type to bigint','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(423,'create correlation table v1',replace('CREATE TABLE IF NOT EXISTS `correlation` (\n`uid` TEXT NOT NULL\n, `source_uid` TEXT NOT NULL\n, `target_uid` TEXT NULL\n, `label` TEXT NOT NULL\n, `description` TEXT NOT NULL\n, PRIMARY KEY ( `uid`,`source_uid` ));','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(424,'add index correlations.uid','CREATE INDEX `IDX_correlation_uid` ON `correlation` (`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(425,'add index correlations.source_uid','CREATE INDEX `IDX_correlation_source_uid` ON `correlation` (`source_uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(426,'add correlation config column','alter table `correlation` ADD COLUMN `config` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(427,'create entity_events table',replace('CREATE TABLE IF NOT EXISTS `entity_event` (\n`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL\n, `entity_id` TEXT NOT NULL\n, `event_type` TEXT NOT NULL\n, `created` INTEGER NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(428,'create dashboard public config v1',replace('CREATE TABLE IF NOT EXISTS `dashboard_public_config` (\n`uid` TEXT PRIMARY KEY NOT NULL\n, `dashboard_uid` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `time_settings` TEXT NOT NULL\n, `refresh_rate` INTEGER NOT NULL DEFAULT 30\n, `template_variables` TEXT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(429,'drop index UQE_dashboard_public_config_uid - v1','DROP INDEX `UQE_dashboard_public_config_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(430,'drop index IDX_dashboard_public_config_org_id_dashboard_uid - v1','DROP INDEX `IDX_dashboard_public_config_org_id_dashboard_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(431,'Drop old dashboard public config table','DROP TABLE IF EXISTS `dashboard_public_config`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(432,'recreate dashboard public config v1',replace('CREATE TABLE IF NOT EXISTS `dashboard_public_config` (\n`uid` TEXT PRIMARY KEY NOT NULL\n, `dashboard_uid` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `time_settings` TEXT NOT NULL\n, `refresh_rate` INTEGER NOT NULL DEFAULT 30\n, `template_variables` TEXT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(433,'create index UQE_dashboard_public_config_uid - v1','CREATE UNIQUE INDEX `UQE_dashboard_public_config_uid` ON `dashboard_public_config` (`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(434,'create index IDX_dashboard_public_config_org_id_dashboard_uid - v1','CREATE INDEX `IDX_dashboard_public_config_org_id_dashboard_uid` ON `dashboard_public_config` (`org_id`,`dashboard_uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(435,'drop index UQE_dashboard_public_config_uid - v2','DROP INDEX `UQE_dashboard_public_config_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(436,'drop index IDX_dashboard_public_config_org_id_dashboard_uid - v2','DROP INDEX `IDX_dashboard_public_config_org_id_dashboard_uid`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(437,'Drop public config table','DROP TABLE IF EXISTS `dashboard_public_config`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(438,'Recreate dashboard public config v2',replace('CREATE TABLE IF NOT EXISTS `dashboard_public_config` (\n`uid` TEXT PRIMARY KEY NOT NULL\n, `dashboard_uid` TEXT NOT NULL\n, `org_id` INTEGER NOT NULL\n, `time_settings` TEXT NULL\n, `template_variables` TEXT NULL\n, `access_token` TEXT NOT NULL\n, `created_by` INTEGER NOT NULL\n, `updated_by` INTEGER NULL\n, `created_at` DATETIME NOT NULL\n, `updated_at` DATETIME NULL\n, `is_enabled` INTEGER NOT NULL DEFAULT 0\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(439,'create index UQE_dashboard_public_config_uid - v2','CREATE UNIQUE INDEX `UQE_dashboard_public_config_uid` ON `dashboard_public_config` (`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(440,'create index IDX_dashboard_public_config_org_id_dashboard_uid - v2','CREATE INDEX `IDX_dashboard_public_config_org_id_dashboard_uid` ON `dashboard_public_config` (`org_id`,`dashboard_uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(441,'create index UQE_dashboard_public_config_access_token - v2','CREATE UNIQUE INDEX `UQE_dashboard_public_config_access_token` ON `dashboard_public_config` (`access_token`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(442,'Rename table dashboard_public_config to dashboard_public - v2','ALTER TABLE `dashboard_public_config` RENAME TO `dashboard_public`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(443,'add annotations_enabled column','alter table `dashboard_public` ADD COLUMN `annotations_enabled` INTEGER NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(444,'create default alerting folders','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(445,'create file table',replace('CREATE TABLE IF NOT EXISTS `file` (\n`path` TEXT NOT NULL\n, `path_hash` TEXT NOT NULL\n, `parent_folder_path_hash` TEXT NOT NULL\n, `contents` BLOB NOT NULL\n, `etag` TEXT NOT NULL\n, `cache_control` TEXT NOT NULL\n, `content_disposition` TEXT NOT NULL\n, `updated` DATETIME NOT NULL\n, `created` DATETIME NOT NULL\n, `size` INTEGER NOT NULL\n, `mime_type` TEXT NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(446,'file table idx: path natural pk','CREATE UNIQUE INDEX `UQE_file_path_hash` ON `file` (`path_hash`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(447,'file table idx: parent_folder_path_hash fast folder retrieval','CREATE INDEX `IDX_file_parent_folder_path_hash` ON `file` (`parent_folder_path_hash`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(448,'create file_meta table',replace('CREATE TABLE IF NOT EXISTS `file_meta` (\n`path_hash` TEXT NOT NULL\n, `key` TEXT NOT NULL\n, `value` TEXT NOT NULL\n);','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(449,'file table idx: path key','CREATE UNIQUE INDEX `UQE_file_meta_path_hash_key` ON `file_meta` (`path_hash`,`key`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(450,'set path collation in file table','SELECT 0;',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(451,'managed permissions migration','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(452,'managed folder permissions alert actions migration','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(453,'RBAC action name migrator','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(454,'Add UID column to playlist','alter table `playlist` ADD COLUMN `uid` TEXT NOT NULL DEFAULT 0 ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(455,'Update uid column values in playlist','UPDATE playlist SET uid=printf(''%d'',id);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(456,'Add index for uid in playlist','CREATE UNIQUE INDEX `UQE_playlist_org_id_uid` ON `playlist` (`org_id`,`uid`);',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(457,'update group index for alert rules','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(458,'managed folder permissions alert actions repeated migration','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(459,'admin only folder/dashboard permission','code migration',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(460,'add action column to seed_assignment','alter table `seed_assignment` ADD COLUMN `action` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(461,'add scope column to seed_assignment','alter table `seed_assignment` ADD COLUMN `scope` TEXT NULL ',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(462,'remove unique index builtin_role_role_name before nullable update','DROP INDEX `UQE_seed_assignment_builtin_role_role_name`',1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(463,'update seed_assignment role_name column to nullable',replace('ALTER TABLE seed_assignment ADD COLUMN tmp_role_name VARCHAR(190) DEFAULT NULL;\nUPDATE seed_assignment SET tmp_role_name = role_name;\nALTER TABLE seed_assignment DROP COLUMN role_name;\nALTER TABLE seed_assignment RENAME COLUMN tmp_role_name TO role_name;','\n',char(10)),1,'','2022-12-02 18:49:20');
INSERT INTO migration_log VALUES(464,'add unique index builtin_role_name back','CREATE UNIQUE INDEX `UQE_seed_assignment_builtin_role_role_name` ON `seed_assignment` (`builtin_role`,`role_name`);',1,'','2022-12-02 18:49:21');
INSERT INTO migration_log VALUES(465,'add unique index builtin_role_action_scope','CREATE UNIQUE INDEX `UQE_seed_assignment_builtin_role_action_scope` ON `seed_assignment` (`builtin_role`,`action`,`scope`);',1,'','2022-12-02 18:49:21');
INSERT INTO migration_log VALUES(466,'add primary key to seed_assigment','code migration',1,'','2022-12-02 18:49:21');
INSERT INTO migration_log VALUES(467,'managed folder permissions alert actions repeated fixed migration','code migration',1,'','2022-12-02 18:49:21');
INSERT INTO migration_log VALUES(468,'migrate external alertmanagers to datsourcse','migrate external alertmanagers to datasource',1,'','2022-12-02 18:49:21');
CREATE TABLE `user` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `version` INTEGER NOT NULL
, `login` TEXT NOT NULL
, `email` TEXT NOT NULL
, `name` TEXT NULL
, `password` TEXT NULL
, `salt` TEXT NULL
, `rands` TEXT NULL
, `company` TEXT NULL
, `org_id` INTEGER NOT NULL
, `is_admin` INTEGER NOT NULL
, `email_verified` INTEGER NULL
, `theme` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `help_flags1` INTEGER NOT NULL DEFAULT 0, `last_seen_at` DATETIME NULL, `is_disabled` INTEGER NOT NULL DEFAULT 0, is_service_account BOOLEAN DEFAULT 0);
INSERT INTO user VALUES(1,0,'admin','admin@localhost','','39284ec7f0c770e20d48c10bc83f91b5f533153b9dee790499d9632a52dfa39a23bcbbd08439874324fcb0e417ceac0ba07e','JBQT8k3tRb','CI4zfl36r6','',1,1,0,'','2020-02-18 16:17:55','2020-02-18 16:18:30',0,'2022-12-02 19:23:07',0,0);
CREATE TABLE `star` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `user_id` INTEGER NOT NULL
, `dashboard_id` INTEGER NOT NULL
);
INSERT INTO star VALUES(1,1,2);
CREATE TABLE `org` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `version` INTEGER NOT NULL
, `name` TEXT NOT NULL
, `address1` TEXT NULL
, `address2` TEXT NULL
, `city` TEXT NULL
, `state` TEXT NULL
, `zip_code` TEXT NULL
, `country` TEXT NULL
, `billing_email` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO org VALUES(1,0,'Red Hat','','','','','','',NULL,'2020-02-18 16:17:55','2020-02-18 18:44:14');
CREATE TABLE `org_user` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `user_id` INTEGER NOT NULL
, `role` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO org_user VALUES(1,1,1,'Admin','2020-02-18 16:17:55','2020-02-18 16:17:55');
CREATE TABLE `dashboard_tag` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `dashboard_id` INTEGER NOT NULL
, `term` TEXT NOT NULL
);
CREATE TABLE `dashboard` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `version` INTEGER NOT NULL
, `slug` TEXT NOT NULL
, `title` TEXT NOT NULL
, `data` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `updated_by` INTEGER NULL, `created_by` INTEGER NULL, `gnet_id` INTEGER NULL, `plugin_id` TEXT NULL, `folder_id` INTEGER NOT NULL DEFAULT 0, `is_folder` INTEGER NOT NULL DEFAULT 0, `has_acl` INTEGER NOT NULL DEFAULT 0, `uid` TEXT NULL, `is_public` INTEGER NOT NULL DEFAULT 0);
INSERT INTO dashboard VALUES(1,1,'postgresql-performance','PostgreSQL Performance','{"schemaVersion":17,"title":"PostgreSQL Performance","uid":"JHYrdoQWz","version":1}',1,'2020-02-18 16:38:22','2020-02-18 16:38:22',1,1,0,'',0,1,0,'JHYrdoQWz',0);
INSERT INTO dashboard VALUES(2,17,'postgresql-statement-statistics','PostgreSQL Statement Statistics',X'7b22616e6e6f746174696f6e73223a7b226c697374223a5b7b226275696c74496e223a312c2264617461736f75726365223a7b2274797065223a2264617461736f75726365222c22756964223a2267726166616e61227d2c22656e61626c65223a747275652c2268696465223a747275652c2269636f6e436f6c6f72223a227267626128302c203231312c203235352c203129222c226e616d65223a22416e6e6f746174696f6e73205c753030323620416c65727473222c22746172676574223a7b226c696d6974223a3130302c226d61746368416e79223a66616c73652c2274616773223a5b5d2c2274797065223a2264617368626f617264227d2c2274797065223a2264617368626f617264227d5d7d2c226564697461626c65223a747275652c2266697363616c5965617253746172744d6f6e7468223a302c226772617068546f6f6c746970223a302c226964223a322c226c696e6b73223a5b5d2c226c6976654e6f77223a66616c73652c2270616e656c73223a5b7b22636f6c756d6e73223a5b5d2c2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f6e7453697a65223a2231303025222c2267726964506f73223a7b2268223a31322c2277223a32342c2278223a302c2279223a307d2c226964223a322c2273686f77486561646572223a747275652c22736f7274223a7b22636f6c223a302c2264657363223a747275657d2c227374796c6573223a5b7b22616c696173223a226d61785f74696d65286d7329222c22616c69676e223a227269676874222c22636f6c6f724d6f6465223a2276616c7565222c22636f6c6f7273223a5b22726762612835302c203137322c2034352c20302e393729222c2272676261283233372c203132392c2034302c20302e383929222c2272676261283234352c2035342c2035342c20302e3929225d2c22646563696d616c73223a342c227061747465726e223a226d61785f74696d65222c227468726573686f6c6473223a5b2231303030222c2232303030225d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a226d65616e5f74696d65286d7329222c22616c69676e223a227269676874222c22636f6c6f724d6f6465223a2276616c7565222c22636f6c6f7273223a5b22726762612835302c203137322c2034352c20302e393729222c2272676261283233372c203132392c2034302c20302e383929222c2272676261283234352c2035342c2035342c20302e3929225d2c22646563696d616c73223a342c227061747465726e223a226d65616e5f74696d65222c227468726573686f6c6473223a5b2231303030222c2232303030225d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a22222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a302c226d617070696e6754797065223a312c227061747465726e223a2263616c6c73222c227468726573686f6c6473223a5b5d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a22222c22616c69676e223a226c656674222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a322c226d617070696e6754797065223a312c227061747465726e223a227175657279222c227072657365727665466f726d6174223a66616c73652c227468726573686f6c6473223a5b5d2c2274797065223a22737472696e67222c22756e6974223a2273686f7274227d5d2c2274617267657473223a5b7b2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22656469746f724d6f6465223a22636f6465222c22666f726d6174223a227461626c65222c2267726f7570223a5b5d2c226d6574726963436f6c756d6e223a226e6f6e65222c227261775175657279223a747275652c2272617753716c223a2253454c4543545c6e20206d65616e5f657865635f74696d652c5c6e20206d61785f657865635f74696d652c5c6e202063616c6c732c5c6e202071756572795c6e46524f4d2070675f737461745f73746174656d656e74735c6e4f5244455220425920312064657363222c227265664964223a2241222c2273656c656374223a5b5b7b22706172616d73223a5b226d61785f74696d65225d2c2274797065223a22636f6c756d6e227d5d5d2c2273716c223a7b22636f6c756d6e73223a5b7b22706172616d6574657273223a5b5d2c2274797065223a2266756e6374696f6e227d5d2c2267726f75704279223a5b7b2270726f7065727479223a7b2274797065223a22737472696e67227d2c2274797065223a2267726f75704279227d5d2c226c696d6974223a35307d2c227461626c65223a2270675f737461745f73746174656d656e7473222c2274696d65436f6c756d6e223a226e6f772829222c2274696d65436f6c756d6e54797065223a22666c6f617438222c227768657265223a5b5d7d5d2c227469746c65223a2253746174656d656e742053746174697374696373222c227472616e73666f726d223a227461626c65222c2274797065223a227461626c652d6f6c64227d2c7b22636f6c756d6e73223a5b5d2c2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f6e7453697a65223a2231303025222c2267726964506f73223a7b2268223a362c2277223a352c2278223a302c2279223a31327d2c226964223a342c2273686f77486561646572223a747275652c22736f7274223a7b22636f6c223a302c2264657363223a747275657d2c227374796c6573223a5b7b22616c696173223a227374617465222c22616c69676e223a226175746f222c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c227061747465726e223a227374617465222c227468726573686f6c6473223a5b22225d2c2274797065223a22737472696e67227d2c7b22616c696173223a22636f756e74222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c22646563696d616c73223a302c227061747465726e223a22636f756e74222c227468726573686f6c6473223a5b223530222c22313030225d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a22746f74616c222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a302c226d617070696e6754797065223a312c227061747465726e223a22746f74616c222c227468726573686f6c6473223a5b5d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a22706374222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a322c226d617070696e6754797065223a312c227061747465726e223a22706374222c227468726573686f6c6473223a5b5d2c2274797065223a226e756d626572222c22756e6974223a2270657263656e74756e6974227d5d2c2274617267657473223a5b7b2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f726d6174223a227461626c65222c2267726f7570223a5b5d2c226d6574726963436f6c756d6e223a226e6f6e65222c227261775175657279223a747275652c2272617753716c223a2273656c65637420782e73746174652c205c6e20202020202020782e5c22636f756e745c222c5c6e20202020202020792e5c22746f74616c5c222c5c6e2020202020202028782e5c22636f756e745c223a3a6e756d657269632831302c3429202f20792e5c22746f74616c5c223a3a6e756d657269632831302c3429293a3a6e756d657269632831302c3429206173205c227063745c225c6e202066726f6d20285c6e20202020202020202073656c656374205c2273746174655c222c5c6e20202020202020202020202020202020636f756e74282a29206173205c22636f756e745c225c6e202020202020202020202066726f6d2070675f737461745f61637469766974795c6e202020202020202020207768657265207573656e616d65206973206e6f74206e756c6c205c6e202020202020202020202020616e64207573656e616d6520213d202764626d6f6e69746f72275c6e202020202020202020202020616e64207374617465206973206e6f74206e756c6c5c6e2020202020202020202067726f7570205c6e202020202020202020202020206279205c2273746174655c225c6e202020202020202920617320785c6e2063726f73735c6e20206a6f696e20285c6e20202020202020202073656c65637420636f756e74282a29206173205c22746f74616c5c225c6e202020202020202020202066726f6d2070675f737461745f61637469766974795c6e202020202020202020207768657265207573656e616d65206973206e6f74206e756c6c205c6e202020202020202020202020616e64207573656e616d6520213d202764626d6f6e69746f72275c6e202020202020202020202020616e64207374617465206973206e6f74206e756c6c5c6e202020202020202920617320795c6e206f72646572205c6e20202020627920782e5c2273746174655c223b5c6e222c227265664964223a2241222c2273656c656374223a5b5b7b22706172616d73223a5b2276616c7565225d2c2274797065223a22636f6c756d6e227d5d5d2c2274696d65436f6c756d6e223a2274696d65222c227768657265223a5b7b226e616d65223a22245f5f74696d6546696c746572222c22706172616d73223a5b5d2c2274797065223a226d6163726f227d5d7d5d2c227469746c65223a225175657279205374617465222c227472616e73666f726d223a227461626c65222c2274797065223a227461626c652d6f6c64227d2c7b22636f6c756d6e73223a5b5d2c2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f6e7453697a65223a2231303025222c2267726964506f73223a7b2268223a372c2277223a31392c2278223a352c2279223a31327d2c226964223a382c2273686f77486561646572223a747275652c22736f7274223a7b22636f6c223a302c2264657363223a747275657d2c227374796c6573223a5b7b22616c696173223a22222c22616c69676e223a227269676874222c22636f6c6f724d6f6465223a2276616c7565222c22636f6c6f7273223a5b22726762612835302c203137322c2034352c20302e393729222c2272676261283233372c203132392c2034302c20302e383929222c2272676261283234352c2035342c2035342c20302e3929225d2c22646563696d616c73223a342c227061747465726e223a22656c6170736564222c227468726573686f6c6473223a5b22313030302e30222c22323030302e30225d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d2c7b22616c696173223a22222c22616c69676e223a226c656674222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a322c226d617070696e6754797065223a312c227061747465726e223a22776169745f74797065222c227468726573686f6c6473223a5b5d2c2274797065223a22737472696e67222c22756e6974223a2273686f7274227d2c7b22616c696173223a22222c22616c69676e223a226175746f222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a322c226d617070696e6754797065223a312c227061747465726e223a227175657279222c227468726573686f6c6473223a5b5d2c2274797065223a22737472696e67222c22756e6974223a2273686f7274227d5d2c2274617267657473223a5b7b2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f726d6174223a227461626c65222c2267726f7570223a5b5d2c226d6574726963436f6c756d6e223a226e6f6e65222c227261775175657279223a747275652c2272617753716c223a2273656c65637420657874726163742865706f63682066726f6d20286e6f772829202d2071756572795f737461727429293a3a6e756d657269632831322c3429206173205c22656c61707365645c222c5c6e20202020202020776169745f6576656e745f74797065206173205c22776169745f747970655c222c5c6e2020202020202071756572795c6e202066726f6d2070675f737461745f61637469766974795c6e207768657265207374617465203d2027616374697665275c6e202020616e64207573656e616d6520213d202764626d6f6e69746f72275c6e206f72646572205c6e202020206279203120646573633b222c227265664964223a2241222c2273656c656374223a5b5b7b22706172616d73223a5b2276616c7565225d2c2274797065223a22636f6c756d6e227d5d5d2c2274696d65436f6c756d6e223a2274696d65222c227768657265223a5b7b226e616d65223a22245f5f74696d6546696c746572222c22706172616d73223a5b5d2c2274797065223a226d6163726f227d5d7d5d2c227469746c65223a224163746976652051756572792054696d6573222c227472616e73666f726d223a227461626c65222c2274797065223a227461626c652d6f6c64227d2c7b22636f6c756d6e73223a5b5d2c2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f6e7453697a65223a2231303025222c2267726964506f73223a7b2268223a362c2277223a352c2278223a302c2279223a31387d2c226964223a362c2273686f77486561646572223a747275652c22736f7274223a7b22636f6c223a302c2264657363223a747275657d2c227374796c6573223a5b7b22616c696173223a2254696d65222c22616c69676e223a226c656674222c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c227061747465726e223a22776169745f6576656e745f74797065222c2274797065223a22737472696e67227d2c7b22616c696173223a22222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c2264617465466f726d6174223a22595959592d4d4d2d44442048483a6d6d3a7373222c22646563696d616c73223a322c226d617070696e6754797065223a312c227061747465726e223a22706374222c227468726573686f6c6473223a5b5d2c2274797065223a226e756d626572222c22756e6974223a2270657263656e74756e6974227d2c7b22616c696173223a22222c22616c69676e223a227269676874222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c22646563696d616c73223a302c227061747465726e223a222f2e2a2f222c227468726573686f6c6473223a5b5d2c2274797065223a226e756d626572222c22756e6974223a226e6f6e65227d5d2c2274617267657473223a5b7b2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f726d6174223a227461626c65222c2267726f7570223a5b5d2c226d6574726963436f6c756d6e223a226e6f6e65222c227261775175657279223a747275652c2272617753716c223a2273656c65637420782e776169745f6576656e745f747970652c205c725c6e20202020202020782e5c22636f756e745c222c5c725c6e20202020202020792e5c22746f74616c5c222c5c725c6e2020202020202063617365207768656e20792e5c22746f74616c5c22203d2030207468656e20302e303a3a6e756d657269632831302c342920656c73652028782e5c22636f756e745c223a3a6e756d657269632831302c3429202f20792e5c22746f74616c5c223a3a6e756d657269632831302c3429293a3a6e756d657269632831302c342920656e643a3a6e756d657269632831302c3429206173205c227063745c225c725c6e202066726f6d20285c725c6e20202020202020202073656c656374205c22776169745f6576656e745f747970655c222c5c725c6e20202020202020202020202020202020636f756e74282a29206173205c22636f756e745c225c725c6e202020202020202020202066726f6d2070675f737461745f61637469766974795c725c6e202020202020202020207768657265207573656e616d65206973206e6f74206e756c6c205c725c6e202020202020202020202020616e64207573656e616d6520213d202764626d6f6e69746f72275c725c6e202020202020202020202020616e6420776169745f6576656e745f74797065206973206e6f74206e756c6c5c725c6e202020202020202020202020616e6420737461746520213d202769646c65275c725c6e2020202020202020202067726f7570205c725c6e202020202020202020202020206279205c22776169745f6576656e745f747970655c225c725c6e202020202020202920617320785c725c6e2063726f73735c725c6e20206a6f696e20285c725c6e20202020202020202073656c65637420636f756e74282a29206173205c22746f74616c5c225c725c6e202020202020202020202066726f6d2070675f737461745f61637469766974795c725c6e202020202020202020207768657265207573656e616d65206973206e6f74206e756c6c205c725c6e202020202020202020202020616e64207573656e616d6520213d202764626d6f6e69746f72275c725c6e202020202020202020202020616e6420776169745f6576656e745f74797065206973206e6f74206e756c6c5c725c6e202020202020202020202020616e6420737461746520213d202769646c65275c725c6e202020202020202920617320795c725c6e206f72646572205c725c6e20202020627920782e5c22776169745f6576656e745f747970655c223b5c725c6e222c227265664964223a2241222c2273656c656374223a5b5b7b22706172616d73223a5b2276616c7565225d2c2274797065223a22636f6c756d6e227d5d5d2c2274696d65436f6c756d6e223a2274696d65222c227768657265223a5b7b226e616d65223a22245f5f74696d6546696c746572222c22706172616d73223a5b5d2c2274797065223a226d6163726f227d5d7d5d2c227469746c65223a2251756572792057616974205479706573222c227472616e73666f726d223a227461626c65222c2274797065223a227461626c652d6f6c64227d2c7b22636f6c756d6e73223a5b5d2c2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f6e7453697a65223a2231303025222c2267726964506f73223a7b2268223a352c2277223a31392c2278223a352c2279223a31397d2c226964223a31302c2273686f77486561646572223a747275652c22736f7274223a7b22636f6c223a302c2264657363223a747275657d2c227374796c6573223a5b7b22616c696173223a22222c22616c69676e223a226c656674222c22636f6c6f7273223a5b2272676261283234352c2035342c2035342c20302e3929222c2272676261283233372c203132392c2034302c20302e383929222c22726762612835302c203137322c2034352c20302e393729225d2c22646563696d616c73223a322c227061747465726e223a222f2e2a2f222c227468726573686f6c6473223a5b5d2c2274797065223a22737472696e67222c22756e6974223a2273686f7274227d5d2c2274617267657473223a5b7b2264617461736f75726365223a7b2274797065223a22706f737467726573222c22756964223a22303030303030303031227d2c22666f726d6174223a227461626c65222c2267726f7570223a5b5d2c226d6574726963436f6c756d6e223a226e6f6e65222c227261775175657279223a747275652c2272617753716c223a2273656c65637420776169745f6576656e745f747970652c5c6e20202020202020776169745f6576656e742c5c6e2020202020202071756572795c6e202066726f6d2070675f737461745f61637469766974795c6e207768657265207573656e616d65206973206e6f74206e756c6c5c6e202020616e64207573656e616d6520213d202764626d6f6e69746f72275c6e202020616e64207374617465203d2027616374697665275c6e202020616e6420776169745f6576656e745f74797065206973206e6f74206e756c6c3b5c6e222c227265664964223a2241222c2273656c656374223a5b5b7b22706172616d73223a5b2276616c7565225d2c2274797065223a22636f6c756d6e227d5d5d2c2274696d65436f6c756d6e223a2274696d65222c227768657265223a5b7b226e616d65223a22245f5f74696d6546696c746572222c22706172616d73223a5b5d2c2274797065223a226d6163726f227d5d7d5d2c227469746c65223a22517565727920576169742044657461696c222c227472616e73666f726d223a227461626c65222c2274797065223a227461626c652d6f6c64227d5d2c2272656672657368223a223573222c22736368656d6156657273696f6e223a33372c227374796c65223a226461726b222c2274616773223a5b5d2c2274656d706c6174696e67223a7b226c697374223a5b5d7d2c2274696d65223a7b2266726f6d223a226e6f772d3668222c22746f223a226e6f77227d2c2274696d657069636b6572223a7b2268696464656e223a66616c73652c22726566726573685f696e74657276616c73223a5b223173222c223273222c223573222c22313073225d7d2c2274696d657a6f6e65223a22222c227469746c65223a22506f737467726553514c2053746174656d656e742053746174697374696373222c22756964223a22797971434f6f51577a222c2276657273696f6e223a31372c227765656b5374617274223a22227d',1,'2020-02-18 16:39:04','2022-12-02 19:22:24',1,1,0,'',1,0,0,'yyqCOoQWz',0);
CREATE TABLE `dashboard_provisioning` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `dashboard_id` INTEGER NULL
, `name` TEXT NOT NULL
, `external_id` TEXT NOT NULL
, `updated` INTEGER NOT NULL DEFAULT 0
, `check_sum` TEXT NULL);
CREATE TABLE `data_source` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `version` INTEGER NOT NULL
, `type` TEXT NOT NULL
, `name` TEXT NOT NULL
, `access` TEXT NOT NULL
, `url` TEXT NOT NULL
, `password` TEXT NULL
, `user` TEXT NULL
, `database` TEXT NULL
, `basic_auth` INTEGER NOT NULL
, `basic_auth_user` TEXT NULL
, `basic_auth_password` TEXT NULL
, `is_default` INTEGER NOT NULL
, `json_data` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `with_credentials` INTEGER NOT NULL DEFAULT 0, `secure_json_data` TEXT NULL, `read_only` INTEGER NULL, `uid` TEXT NOT NULL DEFAULT 0);
INSERT INTO data_source VALUES(1,1,3,'postgres','PostgreSQL','proxy','koku-db:5432','','dbmonitor','postgres',0,'','',1,X'7b22706f73746772657356657273696f6e223a313030302c2273736c6d6f6465223a2264697361626c65227d','2020-02-18 16:18:38','2022-12-02 19:03:52',0,'{"password":"I2VIaFdVblZqUzFaciMqWVdWekxXTm1ZZyp0T2wydVBOMsA+8cNj6pVWq0w7mewyNbuNyjHwzeYNFBw="}',0,'000000001');
CREATE TABLE `api_key` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `name` TEXT NOT NULL
, `key` TEXT NOT NULL
, `role` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `expires` INTEGER NULL, `service_account_id` INTEGER NULL, `last_used_at` DATETIME NULL, `is_revoked` INTEGER NULL DEFAULT 0);
CREATE TABLE `dashboard_snapshot` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `name` TEXT NOT NULL
, `key` TEXT NOT NULL
, `delete_key` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `user_id` INTEGER NOT NULL
, `external` INTEGER NOT NULL
, `external_url` TEXT NOT NULL
, `dashboard` TEXT NOT NULL
, `expires` DATETIME NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `external_delete_url` TEXT NULL, `dashboard_encrypted` BLOB NULL);
CREATE TABLE `quota` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NULL
, `user_id` INTEGER NULL
, `target` TEXT NOT NULL
, `limit` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
CREATE TABLE `plugin_setting` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NULL
, `plugin_id` TEXT NOT NULL
, `enabled` INTEGER NOT NULL
, `pinned` INTEGER NOT NULL
, `json_data` TEXT NULL
, `secure_json_data` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `plugin_version` TEXT NULL);
CREATE TABLE `session` (
`key` TEXT PRIMARY KEY NOT NULL
, `data` BLOB NOT NULL
, `expiry` INTEGER NOT NULL
);
CREATE TABLE `playlist` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `name` TEXT NOT NULL
, `interval` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `uid` TEXT NOT NULL DEFAULT 0);
CREATE TABLE `playlist_item` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `playlist_id` INTEGER NOT NULL
, `type` TEXT NOT NULL
, `value` TEXT NOT NULL
, `title` TEXT NOT NULL
, `order` INTEGER NOT NULL
);
CREATE TABLE `preferences` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `user_id` INTEGER NOT NULL
, `version` INTEGER NOT NULL
, `home_dashboard_id` INTEGER NOT NULL
, `timezone` TEXT NOT NULL
, `theme` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `team_id` INTEGER NULL, `week_start` TEXT NULL, `json_data` TEXT NULL);
INSERT INTO preferences VALUES(1,1,0,0,2,'','','2020-02-18 20:32:54','2020-02-18 20:32:54',0,NULL,NULL);
CREATE TABLE `alert` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `version` INTEGER NOT NULL
, `dashboard_id` INTEGER NOT NULL
, `panel_id` INTEGER NOT NULL
, `org_id` INTEGER NOT NULL
, `name` TEXT NOT NULL
, `message` TEXT NOT NULL
, `state` TEXT NOT NULL
, `settings` TEXT NOT NULL
, `frequency` INTEGER NOT NULL
, `handler` INTEGER NOT NULL
, `severity` TEXT NOT NULL
, `silenced` INTEGER NOT NULL
, `execution_error` TEXT NOT NULL
, `eval_data` TEXT NULL
, `eval_date` DATETIME NULL
, `new_state_date` DATETIME NOT NULL
, `state_changes` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `for` INTEGER NULL);
CREATE TABLE `alert_notification` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `name` TEXT NOT NULL
, `type` TEXT NOT NULL
, `settings` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `is_default` INTEGER NOT NULL DEFAULT 0, `frequency` INTEGER NULL, `send_reminder` INTEGER NULL DEFAULT 0, `disable_resolve_message` INTEGER NOT NULL DEFAULT 0, `uid` TEXT NULL, `secure_settings` TEXT NULL);
CREATE TABLE `alert_notification_state` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `alert_id` INTEGER NOT NULL
, `notifier_id` INTEGER NOT NULL
, `state` TEXT NOT NULL
, `version` INTEGER NOT NULL
, `updated_at` INTEGER NOT NULL
, `alert_rule_state_updated_version` INTEGER NOT NULL
);
CREATE TABLE `annotation` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `alert_id` INTEGER NULL
, `user_id` INTEGER NULL
, `dashboard_id` INTEGER NULL
, `panel_id` INTEGER NULL
, `category_id` INTEGER NULL
, `type` TEXT NOT NULL
, `title` TEXT NOT NULL
, `text` TEXT NOT NULL
, `metric` TEXT NULL
, `prev_state` TEXT NOT NULL
, `new_state` TEXT NOT NULL
, `data` TEXT NOT NULL
, `epoch` INTEGER NOT NULL
, `region_id` INTEGER NULL DEFAULT 0, `tags` TEXT NULL, `created` INTEGER NULL DEFAULT 0, `updated` INTEGER NULL DEFAULT 0, `epoch_end` INTEGER NOT NULL DEFAULT 0);
CREATE TABLE `test_data` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `metric1` TEXT NULL
, `metric2` TEXT NULL
, `value_big_int` INTEGER NULL
, `value_double` REAL NULL
, `value_float` REAL NULL
, `value_int` INTEGER NULL
, `time_epoch` INTEGER NOT NULL
, `time_date_time` DATETIME NOT NULL
, `time_time_stamp` DATETIME NOT NULL
);
CREATE TABLE `dashboard_version` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `dashboard_id` INTEGER NOT NULL
, `parent_version` INTEGER NOT NULL
, `restored_from` INTEGER NOT NULL
, `version` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `created_by` INTEGER NOT NULL
, `message` TEXT NOT NULL
, `data` TEXT NOT NULL
);
INSERT INTO dashboard_version VALUES(1,1,0,0,1,'2020-02-18 16:38:22',1,'','{"schemaVersion":17,"title":"PostgreSQL Performance","uid":"JHYrdoQWz","version":1}');
INSERT INTO dashboard_version VALUES(2,2,0,0,1,'2020-02-18 16:39:04',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":null,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":9,"w":12,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s",""]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":1}');
INSERT INTO dashboard_version VALUES(3,2,1,0,2,'2020-02-18 16:40:30',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":25,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":2}');
INSERT INTO dashboard_version VALUES(4,2,2,0,3,'2020-02-18 16:52:09',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":25,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  max_time,\n  mean_time\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":3}');
INSERT INTO dashboard_version VALUES(5,2,3,0,4,'2020-02-18 16:52:12',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":25,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  max_time,\n  mean_time\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":4}');
INSERT INTO dashboard_version VALUES(6,2,4,0,5,'2020-02-18 16:55:54',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":25,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":5}');
INSERT INTO dashboard_version VALUES(7,2,5,0,6,'2020-02-18 18:32:36',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":6}');
INSERT INTO dashboard_version VALUES(8,2,6,0,7,'2020-02-18 19:14:16',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":7}');
INSERT INTO dashboard_version VALUES(11,2,7,0,8,'2020-02-18 19:40:23',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"aliasColors":{},"bars":false,"dashLength":10,"dashes":false,"datasource":null,"fill":1,"fillGradient":0,"gridPos":{"h":8,"w":12,"x":0,"y":0},"hiddenSeries":false,"id":4,"legend":{"avg":false,"current":false,"max":false,"min":false,"show":true,"total":false,"values":false},"lines":true,"linewidth":1,"nullPointMode":"null","options":{"dataLinks":[]},"percentage":false,"pointradius":2,"points":false,"renderer":"flot","seriesOverrides":[],"spaceLength":10,"stack":false,"steppedLine":false,"targets":[{"format":"time_series","group":[],"metricColumn":"none","rawQuery":false,"rawSql":"SELECT\n  $__time(time_column),\n  value1\nFROM\n  metric_table\nWHERE\n  $__timeFilter(time_column)\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"thresholds":[],"timeFrom":null,"timeRegions":[],"timeShift":null,"title":"Panel Title","tooltip":{"shared":true,"sort":0,"value_type":"individual"},"type":"graph","xaxis":{"buckets":null,"mode":"time","name":null,"show":true,"values":[]},"yaxes":[{"format":"short","label":null,"logBase":1,"max":null,"min":null,"show":true},{"format":"short","label":null,"logBase":1,"max":null,"min":null,"show":true}],"yaxis":{"align":false,"alignLevel":null}},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":8},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":8}');
INSERT INTO dashboard_version VALUES(12,2,8,0,9,'2020-02-18 19:41:25',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":true,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":9}');
INSERT INTO dashboard_version VALUES(13,2,9,0,10,'2020-02-18 19:42:21',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"}],"schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":10}');
INSERT INTO dashboard_version VALUES(14,2,10,0,11,'2020-02-18 19:42:40',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":11}');
INSERT INTO dashboard_version VALUES(15,2,11,0,12,'2020-02-18 19:44:48',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"aliasColors":{},"bars":false,"dashLength":10,"dashes":false,"datasource":null,"fill":1,"fillGradient":0,"gridPos":{"h":8,"w":12,"x":0,"y":0},"hiddenSeries":false,"id":6,"legend":{"avg":false,"current":false,"max":false,"min":false,"show":true,"total":false,"values":false},"lines":true,"linewidth":1,"nullPointMode":"null","options":{"dataLinks":[]},"percentage":false,"pointradius":2,"points":false,"renderer":"flot","seriesOverrides":[],"spaceLength":10,"stack":false,"steppedLine":false,"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select 1;","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"thresholds":[],"timeFrom":null,"timeRegions":[],"timeShift":null,"title":"Panel Title","tooltip":{"shared":true,"sort":0,"value_type":"individual"},"type":"graph","xaxis":{"buckets":null,"mode":"time","name":null,"show":true,"values":[]},"yaxes":[{"format":"short","label":null,"logBase":1,"max":null,"min":null,"show":true},{"format":"short","label":null,"logBase":1,"max":null,"min":null,"show":true}],"yaxis":{"align":false,"alignLevel":null}},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":8},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":5,"x":0,"y":20},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":12}');
INSERT INTO dashboard_version VALUES(16,2,12,0,13,'2020-02-18 19:53:31',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":12,"x":0,"y":0},"id":6,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"Time","align":"left","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"wait_event_type","type":"string"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"/.*/","thresholds":[],"type":"number","unit":"none"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.wait_event_type, \r\n       x.\"count\",\r\n       y.\"total\",\r\n       case when y.\"total\" = 0 then 0.0::numeric(10,4) else (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) end::numeric(10,4) as \"pct\"\r\n  from (\r\n         select \"wait_event_type\",\r\n                count(*) as \"count\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n          group \r\n             by \"wait_event_type\"\r\n       ) as x\r\n cross\r\n  join (\r\n         select count(*) as \"total\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n       ) as y\r\n order \r\n    by x.\"wait_event_type\";\r\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Types","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":8},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":8,"w":5,"x":0,"y":20},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":13}');
INSERT INTO dashboard_version VALUES(17,2,13,0,14,'2020-02-18 20:16:10',1,'1.0','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":7,"w":19,"x":5,"y":12},"id":8,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"elapsed","thresholds":["1000.0","2000.0"],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"wait_type","thresholds":[],"type":"string","unit":"short"},{"alias":"","align":"auto","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select extract(epoch from (now() - query_start))::numeric(12,4) as \"elapsed\",\n       wait_event_type as \"wait_type\",\n       query\n  from pg_stat_activity\n where state = ''active''\n   and usename != ''dbmonitor''\n order \n    by 1 desc;","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Active Query Times","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":18},"id":6,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"Time","align":"left","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"wait_event_type","type":"string"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"/.*/","thresholds":[],"type":"number","unit":"none"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.wait_event_type, \r\n       x.\"count\",\r\n       y.\"total\",\r\n       case when y.\"total\" = 0 then 0.0::numeric(10,4) else (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) end::numeric(10,4) as \"pct\"\r\n  from (\r\n         select \"wait_event_type\",\r\n                count(*) as \"count\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n          group \r\n             by \"wait_event_type\"\r\n       ) as x\r\n cross\r\n  join (\r\n         select count(*) as \"total\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n       ) as y\r\n order \r\n    by x.\"wait_event_type\";\r\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Types","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":5,"w":19,"x":5,"y":19},"id":10,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":2,"pattern":"/.*/","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select wait_event_type,\n       wait_event,\n       query\n  from pg_stat_activity\n where usename is not null\n   and usename != ''dbmonitor''\n   and state = ''active''\n   and wait_event_type is not null;\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Detail","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":14}');
INSERT INTO dashboard_version VALUES(18,2,14,0,15,'2020-02-18 20:34:13',1,'very 1.0','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"max_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"mean_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":7,"w":19,"x":5,"y":12},"id":8,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"elapsed","thresholds":["1000.0","2000.0"],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"wait_type","thresholds":[],"type":"string","unit":"short"},{"alias":"","align":"auto","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select extract(epoch from (now() - query_start))::numeric(12,4) as \"elapsed\",\n       wait_event_type as \"wait_type\",\n       query\n  from pg_stat_activity\n where state = ''active''\n   and usename != ''dbmonitor''\n order \n    by 1 desc;","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Active Query Times","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":18},"id":6,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"Time","align":"left","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"wait_event_type","type":"string"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"/.*/","thresholds":[],"type":"number","unit":"none"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.wait_event_type, \r\n       x.\"count\",\r\n       y.\"total\",\r\n       case when y.\"total\" = 0 then 0.0::numeric(10,4) else (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) end::numeric(10,4) as \"pct\"\r\n  from (\r\n         select \"wait_event_type\",\r\n                count(*) as \"count\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n          group \r\n             by \"wait_event_type\"\r\n       ) as x\r\n cross\r\n  join (\r\n         select count(*) as \"total\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n       ) as y\r\n order \r\n    by x.\"wait_event_type\";\r\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Types","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":5,"w":19,"x":5,"y":19},"id":10,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":2,"pattern":"/.*/","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select wait_event_type,\n       wait_event,\n       query\n  from pg_stat_activity\n where usename is not null\n   and usename != ''dbmonitor''\n   and state = ''active''\n   and wait_event_type is not null;\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Detail","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":15}');
INSERT INTO dashboard_version VALUES(19,2,15,0,16,'2020-03-02 17:17:10',1,'smaller intervals','{"annotations":{"list":[{"builtIn":1,"datasource":"-- Grafana --","enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","type":"dashboard"}]},"editable":true,"gnetId":null,"graphTooltip":0,"id":2,"links":[],"panels":[{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"max_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"mean_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_time,\n  max_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"timeFrom":null,"timeShift":null,"title":"Statement Statistics","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":12},"id":4,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query State","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":7,"w":19,"x":5,"y":12},"id":8,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"elapsed","thresholds":["1000.0","2000.0"],"type":"number","unit":"none"},{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"wait_type","thresholds":[],"type":"string","unit":"short"},{"alias":"","align":"auto","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select extract(epoch from (now() - query_start))::numeric(12,4) as \"elapsed\",\n       wait_event_type as \"wait_type\",\n       query\n  from pg_stat_activity\n where state = ''active''\n   and usename != ''dbmonitor''\n order \n    by 1 desc;","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Active Query Times","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":18},"id":6,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"Time","align":"left","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"wait_event_type","type":"string"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"},{"alias":"","align":"right","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"/.*/","thresholds":[],"type":"number","unit":"none"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.wait_event_type, \r\n       x.\"count\",\r\n       y.\"total\",\r\n       case when y.\"total\" = 0 then 0.0::numeric(10,4) else (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) end::numeric(10,4) as \"pct\"\r\n  from (\r\n         select \"wait_event_type\",\r\n                count(*) as \"count\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n          group \r\n             by \"wait_event_type\"\r\n       ) as x\r\n cross\r\n  join (\r\n         select count(*) as \"total\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n       ) as y\r\n order \r\n    by x.\"wait_event_type\";\r\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Types","transform":"table","type":"table"},{"columns":[],"datasource":null,"fontSize":"100%","gridPos":{"h":5,"w":19,"x":5,"y":19},"id":10,"options":{},"pageSize":null,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"left","colorMode":null,"colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":2,"pattern":"/.*/","thresholds":[],"type":"string","unit":"short"}],"targets":[{"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select wait_event_type,\n       wait_event,\n       query\n  from pg_stat_activity\n where usename is not null\n   and usename != ''dbmonitor''\n   and state = ''active''\n   and wait_event_type is not null;\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"timeFrom":null,"timeShift":null,"title":"Query Wait Detail","transform":"table","type":"table"}],"refresh":"5s","schemaVersion":22,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["1s","2s","5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":16}');
INSERT INTO dashboard_version VALUES(20,2,16,0,17,'2022-12-02 19:22:24',1,'','{"annotations":{"list":[{"builtIn":1,"datasource":{"type":"datasource","uid":"grafana"},"enable":true,"hide":true,"iconColor":"rgba(0, 211, 255, 1)","name":"Annotations \u0026 Alerts","target":{"limit":100,"matchAny":false,"tags":[],"type":"dashboard"},"type":"dashboard"}]},"editable":true,"fiscalYearStartMonth":0,"graphTooltip":0,"id":2,"links":[],"liveNow":false,"panels":[{"columns":[],"datasource":{"type":"postgres","uid":"000000001"},"fontSize":"100%","gridPos":{"h":12,"w":24,"x":0,"y":0},"id":2,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"max_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"max_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"mean_time(ms)","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"mean_time","thresholds":["1000","2000"],"type":"number","unit":"none"},{"alias":"","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"calls","thresholds":[],"type":"number","unit":"none"},{"alias":"","align":"left","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","preserveFormat":false,"thresholds":[],"type":"string","unit":"short"}],"targets":[{"datasource":{"type":"postgres","uid":"000000001"},"editorMode":"code","format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"SELECT\n  mean_exec_time,\n  max_exec_time,\n  calls,\n  query\nFROM pg_stat_statements\nORDER BY 1 desc","refId":"A","select":[[{"params":["max_time"],"type":"column"}]],"sql":{"columns":[{"parameters":[],"type":"function"}],"groupBy":[{"property":{"type":"string"},"type":"groupBy"}],"limit":50},"table":"pg_stat_statements","timeColumn":"now()","timeColumnType":"float8","where":[]}],"title":"Statement Statistics","transform":"table","type":"table-old"},{"columns":[],"datasource":{"type":"postgres","uid":"000000001"},"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":12},"id":4,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"state","align":"auto","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"state","thresholds":[""],"type":"string"},{"alias":"count","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"count","thresholds":["50","100"],"type":"number","unit":"none"},{"alias":"total","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":0,"mappingType":1,"pattern":"total","thresholds":[],"type":"number","unit":"none"},{"alias":"pct","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"}],"targets":[{"datasource":{"type":"postgres","uid":"000000001"},"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.state, \n       x.\"count\",\n       y.\"total\",\n       (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) as \"pct\"\n  from (\n         select \"state\",\n                count(*) as \"count\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n          group \n             by \"state\"\n       ) as x\n cross\n  join (\n         select count(*) as \"total\"\n           from pg_stat_activity\n          where usename is not null \n            and usename != ''dbmonitor''\n            and state is not null\n       ) as y\n order \n    by x.\"state\";\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"title":"Query State","transform":"table","type":"table-old"},{"columns":[],"datasource":{"type":"postgres","uid":"000000001"},"fontSize":"100%","gridPos":{"h":7,"w":19,"x":5,"y":12},"id":8,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"right","colorMode":"value","colors":["rgba(50, 172, 45, 0.97)","rgba(237, 129, 40, 0.89)","rgba(245, 54, 54, 0.9)"],"decimals":4,"pattern":"elapsed","thresholds":["1000.0","2000.0"],"type":"number","unit":"none"},{"alias":"","align":"left","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"wait_type","thresholds":[],"type":"string","unit":"short"},{"alias":"","align":"auto","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"query","thresholds":[],"type":"string","unit":"short"}],"targets":[{"datasource":{"type":"postgres","uid":"000000001"},"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select extract(epoch from (now() - query_start))::numeric(12,4) as \"elapsed\",\n       wait_event_type as \"wait_type\",\n       query\n  from pg_stat_activity\n where state = ''active''\n   and usename != ''dbmonitor''\n order \n    by 1 desc;","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"title":"Active Query Times","transform":"table","type":"table-old"},{"columns":[],"datasource":{"type":"postgres","uid":"000000001"},"fontSize":"100%","gridPos":{"h":6,"w":5,"x":0,"y":18},"id":6,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"Time","align":"left","dateFormat":"YYYY-MM-DD HH:mm:ss","pattern":"wait_event_type","type":"string"},{"alias":"","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"dateFormat":"YYYY-MM-DD HH:mm:ss","decimals":2,"mappingType":1,"pattern":"pct","thresholds":[],"type":"number","unit":"percentunit"},{"alias":"","align":"right","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":0,"pattern":"/.*/","thresholds":[],"type":"number","unit":"none"}],"targets":[{"datasource":{"type":"postgres","uid":"000000001"},"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select x.wait_event_type, \r\n       x.\"count\",\r\n       y.\"total\",\r\n       case when y.\"total\" = 0 then 0.0::numeric(10,4) else (x.\"count\"::numeric(10,4) / y.\"total\"::numeric(10,4))::numeric(10,4) end::numeric(10,4) as \"pct\"\r\n  from (\r\n         select \"wait_event_type\",\r\n                count(*) as \"count\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n          group \r\n             by \"wait_event_type\"\r\n       ) as x\r\n cross\r\n  join (\r\n         select count(*) as \"total\"\r\n           from pg_stat_activity\r\n          where usename is not null \r\n            and usename != ''dbmonitor''\r\n            and wait_event_type is not null\r\n            and state != ''idle''\r\n       ) as y\r\n order \r\n    by x.\"wait_event_type\";\r\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"title":"Query Wait Types","transform":"table","type":"table-old"},{"columns":[],"datasource":{"type":"postgres","uid":"000000001"},"fontSize":"100%","gridPos":{"h":5,"w":19,"x":5,"y":19},"id":10,"showHeader":true,"sort":{"col":0,"desc":true},"styles":[{"alias":"","align":"left","colors":["rgba(245, 54, 54, 0.9)","rgba(237, 129, 40, 0.89)","rgba(50, 172, 45, 0.97)"],"decimals":2,"pattern":"/.*/","thresholds":[],"type":"string","unit":"short"}],"targets":[{"datasource":{"type":"postgres","uid":"000000001"},"format":"table","group":[],"metricColumn":"none","rawQuery":true,"rawSql":"select wait_event_type,\n       wait_event,\n       query\n  from pg_stat_activity\n where usename is not null\n   and usename != ''dbmonitor''\n   and state = ''active''\n   and wait_event_type is not null;\n","refId":"A","select":[[{"params":["value"],"type":"column"}]],"timeColumn":"time","where":[{"name":"$__timeFilter","params":[],"type":"macro"}]}],"title":"Query Wait Detail","transform":"table","type":"table-old"}],"refresh":"5s","schemaVersion":37,"style":"dark","tags":[],"templating":{"list":[]},"time":{"from":"now-6h","to":"now"},"timepicker":{"hidden":false,"refresh_intervals":["1s","2s","5s","10s"]},"timezone":"","title":"PostgreSQL Statement Statistics","uid":"yyqCOoQWz","version":17,"weekStart":""}');
CREATE TABLE `team` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `name` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `email` TEXT NULL);
CREATE TABLE `team_member` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `team_id` INTEGER NOT NULL
, `user_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `external` INTEGER NULL, `permission` INTEGER NULL);
CREATE TABLE `dashboard_acl` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `dashboard_id` INTEGER NOT NULL
, `user_id` INTEGER NULL
, `team_id` INTEGER NULL
, `permission` INTEGER NOT NULL DEFAULT 4
, `role` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO dashboard_acl VALUES(1,-1,-1,NULL,NULL,1,'Viewer','2017-06-20','2017-06-20');
INSERT INTO dashboard_acl VALUES(2,-1,-1,NULL,NULL,2,'Editor','2017-06-20','2017-06-20');
CREATE TABLE `tag` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `key` TEXT NOT NULL
, `value` TEXT NOT NULL
);
CREATE TABLE `login_attempt` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `username` TEXT NOT NULL
, `ip_address` TEXT NOT NULL
, `created` INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE `user_auth` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `user_id` INTEGER NOT NULL
, `auth_module` TEXT NOT NULL
, `auth_id` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `o_auth_access_token` TEXT NULL, `o_auth_refresh_token` TEXT NULL, `o_auth_token_type` TEXT NULL, `o_auth_expiry` DATETIME NULL, `o_auth_id_token` TEXT NULL);
CREATE TABLE `server_lock` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `operation_uid` TEXT NOT NULL
, `version` INTEGER NOT NULL
, `last_execution` INTEGER NOT NULL
);
INSERT INTO server_lock VALUES(1,'cleanup expired auth tokens',3,1670006961);
INSERT INTO server_lock VALUES(2,'delete old login attempts',25,1670008761);
CREATE TABLE `user_auth_token` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `user_id` INTEGER NOT NULL
, `auth_token` TEXT NOT NULL
, `prev_auth_token` TEXT NOT NULL
, `user_agent` TEXT NOT NULL
, `client_ip` TEXT NOT NULL
, `auth_token_seen` INTEGER NOT NULL
, `seen_at` INTEGER NULL
, `rotated_at` INTEGER NOT NULL
, `created_at` INTEGER NOT NULL
, `updated_at` INTEGER NOT NULL
, `revoked_at` INTEGER NULL);
INSERT INTO user_auth_token VALUES(5,1,'89f5c9aedb1961d5d37e93e1cd71eff672bbc30ecfe0290805241bbb92586913','b8cac87f081a07782288663f7ba586ac60cb429f98ac90151a620ea0e78dc24a','Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15','172.18.0.1',1,1670008652,1670008652,1670007018,1670007018,0);
CREATE TABLE `cache_data` (
`cache_key` TEXT PRIMARY KEY NOT NULL
, `data` BLOB NOT NULL
, `expires` INTEGER NOT NULL
, `created_at` INTEGER NOT NULL
);
CREATE TABLE `temp_user` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `version` INTEGER NOT NULL
, `email` TEXT NOT NULL
, `name` TEXT NULL
, `role` TEXT NULL
, `code` TEXT NOT NULL
, `status` TEXT NOT NULL
, `invited_by_user_id` INTEGER NULL
, `email_sent` INTEGER NOT NULL
, `email_sent_on` DATETIME NULL
, `remote_addr` TEXT NULL
, `created` INTEGER NOT NULL DEFAULT 0
, `updated` INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE `alert_rule_tag` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `alert_id` INTEGER NOT NULL
, `tag_id` INTEGER NOT NULL
);
CREATE TABLE `annotation_tag` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `annotation_id` INTEGER NOT NULL
, `tag_id` INTEGER NOT NULL
);
CREATE TABLE `short_url` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `uid` TEXT NOT NULL
, `path` TEXT NOT NULL
, `created_by` INTEGER NOT NULL
, `created_at` INTEGER NOT NULL
, `last_seen_at` INTEGER NULL
);
CREATE TABLE `alert_instance` (
"rule_org_id" INTEGER NOT NULL
, "rule_uid" TEXT NOT NULL DEFAULT 0
, `labels` TEXT NOT NULL
, `labels_hash` TEXT NOT NULL
, `current_state` TEXT NOT NULL
, `current_state_since` INTEGER NOT NULL
, `last_eval_time` INTEGER NOT NULL
, `current_state_end` INTEGER NOT NULL DEFAULT 0, `current_reason` TEXT NULL, PRIMARY KEY ( "rule_org_id","rule_uid",`labels_hash` ));
CREATE TABLE `alert_rule` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `title` TEXT NOT NULL
, `condition` TEXT NOT NULL
, `data` TEXT NOT NULL
, `updated` DATETIME NOT NULL
, `interval_seconds` INTEGER NOT NULL DEFAULT 60
, `version` INTEGER NOT NULL DEFAULT 0
, `uid` TEXT NOT NULL DEFAULT 0
, `namespace_uid` TEXT NOT NULL
, `rule_group` TEXT NOT NULL
, `no_data_state` TEXT NOT NULL DEFAULT 'NoData'
, `exec_err_state` TEXT NOT NULL DEFAULT 'Alerting'
, `for` INTEGER NOT NULL DEFAULT 0, `annotations` TEXT NULL, `labels` TEXT NULL, `dashboard_uid` TEXT NULL, `panel_id` INTEGER NULL, `rule_group_idx` INTEGER NOT NULL DEFAULT 1);
CREATE TABLE `alert_rule_version` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `rule_org_id` INTEGER NOT NULL
, `rule_uid` TEXT NOT NULL DEFAULT 0
, `rule_namespace_uid` TEXT NOT NULL
, `rule_group` TEXT NOT NULL
, `parent_version` INTEGER NOT NULL
, `restored_from` INTEGER NOT NULL
, `version` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `title` TEXT NOT NULL
, `condition` TEXT NOT NULL
, `data` TEXT NOT NULL
, `interval_seconds` INTEGER NOT NULL
, `no_data_state` TEXT NOT NULL DEFAULT 'NoData'
, `exec_err_state` TEXT NOT NULL DEFAULT 'Alerting'
, `for` INTEGER NOT NULL DEFAULT 0, `annotations` TEXT NULL, `labels` TEXT NULL, `rule_group_idx` INTEGER NOT NULL DEFAULT 1);
CREATE TABLE `alert_configuration` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `alertmanager_configuration` TEXT NOT NULL
, `configuration_version` TEXT NOT NULL
, `created_at` INTEGER NOT NULL
, `default` INTEGER NOT NULL DEFAULT 0, `org_id` INTEGER NOT NULL DEFAULT 0, `configuration_hash` TEXT NOT NULL DEFAULT 'not-yet-calculated');
INSERT INTO alert_configuration VALUES(1,replace('{\n	"alertmanager_config": {\n		"route": {\n			"receiver": "grafana-default-email",\n			"group_by": ["grafana_folder", "alertname"]\n		},\n		"receivers": [{\n			"name": "grafana-default-email",\n			"grafana_managed_receiver_configs": [{\n				"uid": "",\n				"name": "email receiver",\n				"type": "email",\n				"isDefault": true,\n				"settings": {\n					"addresses": "<example@email.com>"\n				}\n			}]\n		}]\n	}\n}\n','\n',char(10)),'v1',1670006961,1,1,'e0528a75784033ae7b15c40851d89484');
CREATE TABLE `ngalert_configuration` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `alertmanagers` TEXT NULL
, `created_at` INTEGER NOT NULL
, `updated_at` INTEGER NOT NULL
, `send_alerts_to` INTEGER NOT NULL DEFAULT 0);
CREATE TABLE `provenance_type` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `record_key` TEXT NOT NULL
, `record_type` TEXT NOT NULL
, `provenance` TEXT NOT NULL
);
CREATE TABLE `alert_image` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `token` TEXT NOT NULL
, `path` TEXT NOT NULL
, `url` TEXT NOT NULL
, `created_at` DATETIME NOT NULL
, `expires_at` DATETIME NOT NULL
);
CREATE TABLE `library_element` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `folder_id` INTEGER NOT NULL
, `uid` TEXT NOT NULL
, `name` TEXT NOT NULL
, `kind` INTEGER NOT NULL
, `type` TEXT NOT NULL
, `description` TEXT NOT NULL
, `model` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `created_by` INTEGER NOT NULL
, `updated` DATETIME NOT NULL
, `updated_by` INTEGER NOT NULL
, `version` INTEGER NOT NULL
);
CREATE TABLE `library_element_connection` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `element_id` INTEGER NOT NULL
, `kind` INTEGER NOT NULL
, `connection_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `created_by` INTEGER NOT NULL
);
CREATE TABLE `data_keys` (
"name" TEXT PRIMARY KEY NOT NULL
, `active` INTEGER NOT NULL
, `scope` TEXT NOT NULL
, `provider` TEXT NOT NULL
, `encrypted_data` BLOB NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, "label" TEXT NOT NULL DEFAULT '');
INSERT INTO data_keys VALUES('xxVRucKVk',1,'root','secretKey.v1',X'2a5957567a4c574e6d59672a3153533846505654d2d83079b24a4f66a1d09b46ac7dd83ea364432f7637a2e90c01d435f31671e8','2022-12-02 18:49:21','2022-12-02 18:49:21','2022-12-02/root@secretKey.v1');
CREATE TABLE `secrets` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `namespace` TEXT NOT NULL
, `type` TEXT NOT NULL
, `value` TEXT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO secrets VALUES(1,1,'PostgreSQL','datasource','I2VIaFdVblZqUzFaciMqWVdWekxXTm1ZZypsdkVlMXBHMt/CRNyqL/wPn1Xxx5jle9ZJZ5gXw6ey5Qf/BY7mxHH/D8RKh1eex1I','2022-12-02 18:49:21','2022-12-02 19:03:52');
CREATE TABLE `kv_store` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `namespace` TEXT NOT NULL
, `key` TEXT NOT NULL
, `value` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO kv_store VALUES(1,0,'datasource','secretMigrationStatus','compatible','2022-12-02 18:49:21','2022-12-02 18:49:21');
INSERT INTO kv_store VALUES(2,1,'alertmanager','silences','','2022-12-02 19:04:21','2022-12-02 19:04:21');
INSERT INTO kv_store VALUES(3,1,'alertmanager','notifications','','2022-12-02 19:04:21','2022-12-02 19:04:21');
CREATE TABLE `permission` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `role_id` INTEGER NOT NULL
, `action` TEXT NOT NULL
, `scope` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
);
INSERT INTO permission VALUES(1,1,'dashboards:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(2,1,'dashboards:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(3,1,'dashboards:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(4,1,'dashboards:create','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(5,1,'folders:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(6,1,'folders:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(7,1,'folders:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(8,2,'dashboards:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(9,2,'folders:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(10,3,'dashboards:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(11,3,'dashboards:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(12,3,'dashboards:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(13,3,'folders:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(14,3,'folders:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(15,3,'folders:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(16,3,'dashboards:create','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(17,1,'alert.rules:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(18,1,'alert.rules:create','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(19,1,'alert.rules:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(20,1,'alert.rules:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(21,2,'alert.rules:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(22,3,'alert.rules:read','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(23,3,'alert.rules:create','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(24,3,'alert.rules:delete','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
INSERT INTO permission VALUES(25,3,'alert.rules:write','folders:uid:JHYrdoQWz','2022-12-02 18:49:20','2022-12-02 18:49:20');
CREATE TABLE `role` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `name` TEXT NOT NULL
, `description` TEXT NULL
, `version` INTEGER NOT NULL
, `org_id` INTEGER NOT NULL
, `uid` TEXT NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `display_name` TEXT NULL, `group_name` TEXT NULL, `hidden` INTEGER NOT NULL DEFAULT 0);
INSERT INTO role VALUES(1,'managed:builtins:editor:permissions',NULL,1,1,'managed_1_builtins_editor','2022-12-02 18:49:20.760963386+00:00','2022-12-02 18:49:20.760963386+00:00',NULL,NULL,0);
INSERT INTO role VALUES(2,'managed:builtins:viewer:permissions',NULL,1,1,'managed_1_builtins_viewer','2022-12-02 18:49:20.760963386+00:00','2022-12-02 18:49:20.760963386+00:00',NULL,NULL,0);
INSERT INTO role VALUES(3,'managed:builtins:admin:permissions','',0,1,'managed_1_builtins_admin','2022-12-02 18:49:20','2022-12-02 18:49:20','','',0);
CREATE TABLE `team_role` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `team_id` INTEGER NOT NULL
, `role_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
);
CREATE TABLE `user_role` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `org_id` INTEGER NOT NULL
, `user_id` INTEGER NOT NULL
, `role_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
);
CREATE TABLE `builtin_role` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `role` TEXT NOT NULL
, `role_id` INTEGER NOT NULL
, `created` DATETIME NOT NULL
, `updated` DATETIME NOT NULL
, `org_id` INTEGER NOT NULL DEFAULT 0);
INSERT INTO builtin_role VALUES(1,'Editor',1,'2022-12-02 18:49:20','2022-12-02 18:49:20',1);
INSERT INTO builtin_role VALUES(2,'Viewer',2,'2022-12-02 18:49:20','2022-12-02 18:49:20',1);
INSERT INTO builtin_role VALUES(3,'Admin',3,'2022-12-02 18:49:20','2022-12-02 18:49:20',1);
CREATE TABLE `query_history` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `uid` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `datasource_uid` TEXT NOT NULL
, `created_by` INTEGER NOT NULL
, `created_at` INTEGER NOT NULL
, `comment` TEXT NOT NULL
, `queries` TEXT NOT NULL
);
CREATE TABLE `query_history_star` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `query_uid` TEXT NOT NULL
, `user_id` INTEGER NOT NULL
, `org_id` INTEGER NOT NULL DEFAULT 1);
CREATE TABLE `correlation` (
`uid` TEXT NOT NULL
, `source_uid` TEXT NOT NULL
, `target_uid` TEXT NULL
, `label` TEXT NOT NULL
, `description` TEXT NOT NULL
, `config` TEXT NULL, PRIMARY KEY ( `uid`,`source_uid` ));
CREATE TABLE `entity_event` (
`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, `entity_id` TEXT NOT NULL
, `event_type` TEXT NOT NULL
, `created` INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS "dashboard_public" (
`uid` TEXT PRIMARY KEY NOT NULL
, `dashboard_uid` TEXT NOT NULL
, `org_id` INTEGER NOT NULL
, `time_settings` TEXT NULL
, `template_variables` TEXT NULL
, `access_token` TEXT NOT NULL
, `created_by` INTEGER NOT NULL
, `updated_by` INTEGER NULL
, `created_at` DATETIME NOT NULL
, `updated_at` DATETIME NULL
, `is_enabled` INTEGER NOT NULL DEFAULT 0
, `annotations_enabled` INTEGER NOT NULL DEFAULT 0);
CREATE TABLE `file` (
`path` TEXT NOT NULL
, `path_hash` TEXT NOT NULL
, `parent_folder_path_hash` TEXT NOT NULL
, `contents` BLOB NOT NULL
, `etag` TEXT NOT NULL
, `cache_control` TEXT NOT NULL
, `content_disposition` TEXT NOT NULL
, `updated` DATETIME NOT NULL
, `created` DATETIME NOT NULL
, `size` INTEGER NOT NULL
, `mime_type` TEXT NOT NULL
);
CREATE TABLE `file_meta` (
`path_hash` TEXT NOT NULL
, `key` TEXT NOT NULL
, `value` TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS "seed_assignment" (
		    id INTEGER PRIMARY KEY AUTOINCREMENT,
			builtin_role TEXT,
			action TEXT,
			scope TEXT,
			role_name TEXT
		);
DELETE FROM sqlite_sequence;
INSERT INTO sqlite_sequence VALUES('migration_log',468);
INSERT INTO sqlite_sequence VALUES('user',1);
INSERT INTO sqlite_sequence VALUES('dashboard',3);
INSERT INTO sqlite_sequence VALUES('dashboard_provisioning',0);
INSERT INTO sqlite_sequence VALUES('data_source',2);
INSERT INTO sqlite_sequence VALUES('api_key',0);
INSERT INTO sqlite_sequence VALUES('dashboard_version',20);
INSERT INTO sqlite_sequence VALUES('dashboard_acl',2);
INSERT INTO sqlite_sequence VALUES('login_attempt',0);
INSERT INTO sqlite_sequence VALUES('org',1);
INSERT INTO sqlite_sequence VALUES('org_user',1);
INSERT INTO sqlite_sequence VALUES('server_lock',3);
INSERT INTO sqlite_sequence VALUES('user_auth_token',5);
INSERT INTO sqlite_sequence VALUES('star',1);
INSERT INTO sqlite_sequence VALUES('preferences',1);
INSERT INTO sqlite_sequence VALUES('temp_user',0);
INSERT INTO sqlite_sequence VALUES('alert_rule_tag',0);
INSERT INTO sqlite_sequence VALUES('annotation_tag',0);
INSERT INTO sqlite_sequence VALUES('role',3);
INSERT INTO sqlite_sequence VALUES('builtin_role',3);
INSERT INTO sqlite_sequence VALUES('permission',25);
INSERT INTO sqlite_sequence VALUES('seed_assignment',0);
INSERT INTO sqlite_sequence VALUES('alert_configuration',1);
INSERT INTO sqlite_sequence VALUES('secrets',1);
INSERT INTO sqlite_sequence VALUES('kv_store',3);
CREATE UNIQUE INDEX `UQE_user_login` ON `user` (`login`);
CREATE UNIQUE INDEX `UQE_user_email` ON `user` (`email`);
CREATE UNIQUE INDEX `UQE_star_user_id_dashboard_id` ON `star` (`user_id`,`dashboard_id`);
CREATE UNIQUE INDEX `UQE_org_name` ON `org` (`name`);
CREATE INDEX `IDX_org_user_org_id` ON `org_user` (`org_id`);
CREATE UNIQUE INDEX `UQE_org_user_org_id_user_id` ON `org_user` (`org_id`,`user_id`);
CREATE INDEX `IDX_dashboard_org_id` ON `dashboard` (`org_id`);
CREATE INDEX `IDX_dashboard_gnet_id` ON `dashboard` (`gnet_id`);
CREATE INDEX `IDX_dashboard_org_id_plugin_id` ON `dashboard` (`org_id`,`plugin_id`);
CREATE INDEX `IDX_dashboard_tag_dashboard_id` ON `dashboard_tag` (`dashboard_id`);
CREATE UNIQUE INDEX `UQE_dashboard_org_id_uid` ON `dashboard` (`org_id`,`uid`);
CREATE UNIQUE INDEX `UQE_dashboard_org_id_folder_id_title` ON `dashboard` (`org_id`,`folder_id`,`title`);
CREATE INDEX `IDX_dashboard_provisioning_dashboard_id` ON `dashboard_provisioning` (`dashboard_id`);
CREATE INDEX `IDX_dashboard_provisioning_dashboard_id_name` ON `dashboard_provisioning` (`dashboard_id`,`name`);
CREATE INDEX `IDX_data_source_org_id` ON `data_source` (`org_id`);
CREATE UNIQUE INDEX `UQE_data_source_org_id_name` ON `data_source` (`org_id`,`name`);
CREATE INDEX `IDX_api_key_org_id` ON `api_key` (`org_id`);
CREATE UNIQUE INDEX `UQE_api_key_key` ON `api_key` (`key`);
CREATE UNIQUE INDEX `UQE_api_key_org_id_name` ON `api_key` (`org_id`,`name`);
CREATE UNIQUE INDEX `UQE_dashboard_snapshot_key` ON `dashboard_snapshot` (`key`);
CREATE UNIQUE INDEX `UQE_dashboard_snapshot_delete_key` ON `dashboard_snapshot` (`delete_key`);
CREATE INDEX `IDX_dashboard_snapshot_user_id` ON `dashboard_snapshot` (`user_id`);
CREATE UNIQUE INDEX `UQE_quota_org_id_user_id_target` ON `quota` (`org_id`,`user_id`,`target`);
CREATE UNIQUE INDEX `UQE_plugin_setting_org_id_plugin_id` ON `plugin_setting` (`org_id`,`plugin_id`);
CREATE INDEX `IDX_alert_org_id_id` ON `alert` (`org_id`,`id`);
CREATE INDEX `IDX_alert_state` ON `alert` (`state`);
CREATE INDEX `IDX_alert_dashboard_id` ON `alert` (`dashboard_id`);
CREATE UNIQUE INDEX `UQE_alert_notification_state_org_id_alert_id_notifier_id` ON `alert_notification_state` (`org_id`,`alert_id`,`notifier_id`);
CREATE UNIQUE INDEX `UQE_alert_notification_org_id_uid` ON `alert_notification` (`org_id`,`uid`);
CREATE INDEX `IDX_annotation_org_id_alert_id` ON `annotation` (`org_id`,`alert_id`);
CREATE INDEX `IDX_annotation_org_id_type` ON `annotation` (`org_id`,`type`);
CREATE INDEX `IDX_annotation_org_id_created` ON `annotation` (`org_id`,`created`);
CREATE INDEX `IDX_annotation_org_id_updated` ON `annotation` (`org_id`,`updated`);
CREATE INDEX `IDX_annotation_org_id_dashboard_id_epoch_end_epoch` ON `annotation` (`org_id`,`dashboard_id`,`epoch_end`,`epoch`);
CREATE INDEX `IDX_annotation_org_id_epoch_end_epoch` ON `annotation` (`org_id`,`epoch_end`,`epoch`);
CREATE INDEX `IDX_dashboard_version_dashboard_id` ON `dashboard_version` (`dashboard_id`);
CREATE UNIQUE INDEX `UQE_dashboard_version_dashboard_id_version` ON `dashboard_version` (`dashboard_id`,`version`);
CREATE INDEX `IDX_team_org_id` ON `team` (`org_id`);
CREATE UNIQUE INDEX `UQE_team_org_id_name` ON `team` (`org_id`,`name`);
CREATE INDEX `IDX_team_member_org_id` ON `team_member` (`org_id`);
CREATE UNIQUE INDEX `UQE_team_member_org_id_team_id_user_id` ON `team_member` (`org_id`,`team_id`,`user_id`);
CREATE INDEX `IDX_dashboard_acl_dashboard_id` ON `dashboard_acl` (`dashboard_id`);
CREATE UNIQUE INDEX `UQE_dashboard_acl_dashboard_id_user_id` ON `dashboard_acl` (`dashboard_id`,`user_id`);
CREATE UNIQUE INDEX `UQE_dashboard_acl_dashboard_id_team_id` ON `dashboard_acl` (`dashboard_id`,`team_id`);
CREATE UNIQUE INDEX `UQE_tag_key_value` ON `tag` (`key`,`value`);
CREATE INDEX `IDX_login_attempt_username` ON `login_attempt` (`username`);
CREATE INDEX `IDX_user_auth_auth_module_auth_id` ON `user_auth` (`auth_module`,`auth_id`);
CREATE INDEX `IDX_user_auth_user_id` ON `user_auth` (`user_id`);
CREATE UNIQUE INDEX `UQE_server_lock_operation_uid` ON `server_lock` (`operation_uid`);
CREATE UNIQUE INDEX `UQE_user_auth_token_auth_token` ON `user_auth_token` (`auth_token`);
CREATE UNIQUE INDEX `UQE_user_auth_token_prev_auth_token` ON `user_auth_token` (`prev_auth_token`);
CREATE UNIQUE INDEX `UQE_cache_data_cache_key` ON `cache_data` (`cache_key`);
CREATE INDEX `IDX_user_login_email` ON `user` (`login`,`email`);
CREATE INDEX `IDX_temp_user_email` ON `temp_user` (`email`);
CREATE INDEX `IDX_temp_user_org_id` ON `temp_user` (`org_id`);
CREATE INDEX `IDX_temp_user_code` ON `temp_user` (`code`);
CREATE INDEX `IDX_temp_user_status` ON `temp_user` (`status`);
CREATE INDEX `IDX_org_user_user_id` ON `org_user` (`user_id`);
CREATE INDEX `IDX_dashboard_title` ON `dashboard` (`title`);
CREATE INDEX `IDX_dashboard_is_folder` ON `dashboard` (`is_folder`);
CREATE UNIQUE INDEX `UQE_data_source_org_id_uid` ON `data_source` (`org_id`,`uid`);
CREATE INDEX `IDX_data_source_org_id_is_default` ON `data_source` (`org_id`,`is_default`);
CREATE INDEX `IDX_preferences_org_id` ON `preferences` (`org_id`);
CREATE INDEX `IDX_preferences_user_id` ON `preferences` (`user_id`);
CREATE UNIQUE INDEX `UQE_alert_rule_tag_alert_id_tag_id` ON `alert_rule_tag` (`alert_id`,`tag_id`);
CREATE INDEX `IDX_alert_notification_state_alert_id` ON `alert_notification_state` (`alert_id`);
CREATE INDEX `IDX_alert_rule_tag_alert_id` ON `alert_rule_tag` (`alert_id`);
CREATE UNIQUE INDEX `UQE_annotation_tag_annotation_id_tag_id` ON `annotation_tag` (`annotation_id`,`tag_id`);
CREATE INDEX `IDX_annotation_alert_id` ON `annotation` (`alert_id`);
CREATE INDEX `IDX_team_member_team_id` ON `team_member` (`team_id`);
CREATE INDEX `IDX_dashboard_acl_user_id` ON `dashboard_acl` (`user_id`);
CREATE INDEX `IDX_dashboard_acl_team_id` ON `dashboard_acl` (`team_id`);
CREATE INDEX `IDX_dashboard_acl_org_id_role` ON `dashboard_acl` (`org_id`,`role`);
CREATE INDEX `IDX_dashboard_acl_permission` ON `dashboard_acl` (`permission`);
CREATE INDEX `IDX_user_auth_token_user_id` ON `user_auth_token` (`user_id`);
CREATE UNIQUE INDEX `UQE_short_url_org_id_uid` ON `short_url` (`org_id`,`uid`);
CREATE INDEX `IDX_alert_instance_rule_org_id_rule_uid_current_state` ON `alert_instance` (`rule_org_id`,`rule_uid`,`current_state`);
CREATE INDEX `IDX_alert_instance_rule_org_id_current_state` ON `alert_instance` (`rule_org_id`,`current_state`);
CREATE UNIQUE INDEX `UQE_alert_rule_org_id_uid` ON `alert_rule` (`org_id`,`uid`);
CREATE INDEX `IDX_alert_rule_org_id_namespace_uid_rule_group` ON `alert_rule` (`org_id`,`namespace_uid`,`rule_group`);
CREATE UNIQUE INDEX `UQE_alert_rule_org_id_namespace_uid_title` ON `alert_rule` (`org_id`,`namespace_uid`,`title`);
CREATE INDEX `IDX_alert_rule_org_id_dashboard_uid_panel_id` ON `alert_rule` (`org_id`,`dashboard_uid`,`panel_id`);
CREATE UNIQUE INDEX `UQE_alert_rule_version_rule_org_id_rule_uid_version` ON `alert_rule_version` (`rule_org_id`,`rule_uid`,`version`);
CREATE INDEX `IDX_alert_rule_version_rule_org_id_rule_namespace_uid_rule_group` ON `alert_rule_version` (`rule_org_id`,`rule_namespace_uid`,`rule_group`);
CREATE INDEX `IDX_alert_configuration_org_id` ON `alert_configuration` (`org_id`);
CREATE UNIQUE INDEX `UQE_ngalert_configuration_org_id` ON `ngalert_configuration` (`org_id`);
CREATE UNIQUE INDEX `UQE_provenance_type_record_type_record_key_org_id` ON `provenance_type` (`record_type`,`record_key`,`org_id`);
CREATE UNIQUE INDEX `UQE_alert_image_token` ON `alert_image` (`token`);
CREATE UNIQUE INDEX `UQE_library_element_org_id_folder_id_name_kind` ON `library_element` (`org_id`,`folder_id`,`name`,`kind`);
CREATE UNIQUE INDEX `UQE_library_element_connection_element_id_kind_connection_id` ON `library_element_connection` (`element_id`,`kind`,`connection_id`);
CREATE UNIQUE INDEX `UQE_library_element_org_id_uid` ON `library_element` (`org_id`,`uid`);
CREATE UNIQUE INDEX `UQE_kv_store_org_id_namespace_key` ON `kv_store` (`org_id`,`namespace`,`key`);
CREATE INDEX `IDX_permission_role_id` ON `permission` (`role_id`);
CREATE UNIQUE INDEX `UQE_permission_role_id_action_scope` ON `permission` (`role_id`,`action`,`scope`);
CREATE INDEX `IDX_role_org_id` ON `role` (`org_id`);
CREATE UNIQUE INDEX `UQE_role_org_id_name` ON `role` (`org_id`,`name`);
CREATE INDEX `IDX_team_role_org_id` ON `team_role` (`org_id`);
CREATE UNIQUE INDEX `UQE_team_role_org_id_team_id_role_id` ON `team_role` (`org_id`,`team_id`,`role_id`);
CREATE INDEX `IDX_team_role_team_id` ON `team_role` (`team_id`);
CREATE INDEX `IDX_user_role_org_id` ON `user_role` (`org_id`);
CREATE UNIQUE INDEX `UQE_user_role_org_id_user_id_role_id` ON `user_role` (`org_id`,`user_id`,`role_id`);
CREATE INDEX `IDX_user_role_user_id` ON `user_role` (`user_id`);
CREATE INDEX `IDX_builtin_role_role_id` ON `builtin_role` (`role_id`);
CREATE INDEX `IDX_builtin_role_role` ON `builtin_role` (`role`);
CREATE INDEX `IDX_builtin_role_org_id` ON `builtin_role` (`org_id`);
CREATE UNIQUE INDEX `UQE_builtin_role_org_id_role_id_role` ON `builtin_role` (`org_id`,`role_id`,`role`);
CREATE UNIQUE INDEX `UQE_role_uid` ON `role` (`uid`);
CREATE INDEX `IDX_query_history_org_id_created_by_datasource_uid` ON `query_history` (`org_id`,`created_by`,`datasource_uid`);
CREATE UNIQUE INDEX `UQE_query_history_star_user_id_query_uid` ON `query_history_star` (`user_id`,`query_uid`);
CREATE INDEX `IDX_correlation_uid` ON `correlation` (`uid`);
CREATE INDEX `IDX_correlation_source_uid` ON `correlation` (`source_uid`);
CREATE UNIQUE INDEX `UQE_dashboard_public_config_uid` ON "dashboard_public" (`uid`);
CREATE INDEX `IDX_dashboard_public_config_org_id_dashboard_uid` ON "dashboard_public" (`org_id`,`dashboard_uid`);
CREATE UNIQUE INDEX `UQE_dashboard_public_config_access_token` ON "dashboard_public" (`access_token`);
CREATE UNIQUE INDEX `UQE_file_path_hash` ON `file` (`path_hash`);
CREATE INDEX `IDX_file_parent_folder_path_hash` ON `file` (`parent_folder_path_hash`);
CREATE UNIQUE INDEX `UQE_file_meta_path_hash_key` ON `file_meta` (`path_hash`,`key`);
CREATE UNIQUE INDEX `UQE_playlist_org_id_uid` ON `playlist` (`org_id`,`uid`);
CREATE UNIQUE INDEX UQE_seed_assignment_builtin_role_action_scope ON seed_assignment (builtin_role, action, scope);
CREATE UNIQUE INDEX UQE_seed_assignment_builtin_role_role_name ON seed_assignment (builtin_role, role_name);
COMMIT;
