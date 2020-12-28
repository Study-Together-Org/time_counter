# INSERT INTO User (discord_user_id)
# VALUES (791367476235337730);

INSERT INTO Action (User_id, category, detail, creation_time)
VALUES (1, 'exit channel', 'General', '2020-12-25 18:37:07.000000');

SELECT id from User WHERE discord_user_id = 791367476235337730

SELECT table_schema "studytogether",
       ROUND(SUM(data_length + index_length) / 1024 / 1024, 1) "DB Size in MB"
FROM information_schema.tables
GROUP BY table_schema;
