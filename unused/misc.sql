# INSERT INTO User (discord_user_id)
# VALUES (791367476235337730);

INSERT INTO Action (User_id, category, detail, creation_time)
VALUES (1, 'exit channel', 'General', '2020-12-25 18:37:07.000000');

SELECT id from User WHERE discord_user_id = 791367476235337730

SELECT table_schema "studytogether",
       ROUND(SUM(data_length + index_length) / 1024 / 1024, 1) "DB Size in MB"
FROM information_schema.tables
GROUP BY table_schema;

SET @rownum := 0;

SELECT val, id, study_time
FROM (
         SELECT @rownum := @rownum + 1 AS val, id, study_time
         FROM user ORDER BY study_time DESC
     )
         as result

explain SELECT study_time
        FROM (
                 SELECT @rownum := @rownum + 1 AS study_time
                 FROM user ORDER BY study_time DESC
             )
                 as result where study_time = 516.42


explain SELECT creation_time
        FROM action ORDER BY creation_time DESC

SET @mutlplier:= 0;
select user_id, sum(creation_time) as exit_sum from action
where category = 'exit channel'
group by user_id

explain select user_id, sum(creation_time) as exit_sum from action
        where category = 'exit channel'
        group by user_id

select user_id, sum(creation_time) as enter_sum from action
where category = 'enter channel'
group by user_id
