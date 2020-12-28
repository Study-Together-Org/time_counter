SELECT *
FROM (
         SELECT *
         FROM (
                  SELECT *
                  FROM user
                  WHERE
                          user.study_time >= (
                          SELECT study_time
                          FROM user
                          WHERE user.id = 1
                      )
                    AND user.id != 1
                  ORDER BY study_time
                  LIMIT 5
              ) a
         ORDER BY a.study_time DESC
     ) z
UNION ALL
SELECT *
FROM user
WHERE user.id = 1
UNION ALL
SELECT *
FROM (
         SELECT *
         FROM user
         WHERE
                 study_time < (
                 SELECT study_time
                 FROM user
                 WHERE user.id = 1
             )
         ORDER BY study_time DESC
         LIMIT 5
     ) w
