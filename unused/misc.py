# This file contains unused code

# rolesID = [roles[i]['id'] for i in roles]

# role_id = rolesID[bisect.bisect_left(list(role_name_to_begin_hours.values()), hours_cur_month)]
# next_time = list(role_name_to_begin_hours.values())[1]

# agg.set_index("user_id", drop=True, inplace=True)
# agg.to_sql('user', con=self.sqlalchemy_session.bind, if_exists="replace", index=False)
# update_statement = update(User) \
#     .values(study_time=agg["study_time"].loc[User.id])
# self.sqlalchemy_session.execute(update_statement)
# self.sqlalchemy_session.commit()
# agg["rank"] = agg["study_time"].rank(method="first", ascending=False).astype(int)

# async def get_neighbor_stats(self, hours_cur_month):
#     get_lb_query = f"""
#                 SELECT *
#                 FROM (
#                     SELECT *
#                     FROM (
#                         SELECT *
#                         FROM user
#                         WHERE
#                         user.study_time >= {hours_cur_month}
#                         AND user.id != 1
#                         ORDER BY study_time
#                         LIMIT 5
#                     ) a
#                 ORDER BY a.study_time DESC
#                 ) z
#             UNION ALL
#                 SELECT *
#                 FROM user
#                 WHERE user.id = 1
#             UNION ALL
#                 SELECT *
#                 FROM (
#                     SELECT *
#                     FROM user
#                     WHERE
#                     study_time < {hours_cur_month}
#                     ORDER BY study_time DESC
#                     LIMIT 5
#                 ) w
#             order by study_time
#         """
#     print(get_lb_query)
#     response = await self.bot.sql.query(get_lb_query)
#
#     return response

# async def get_user_rank(self, user_id):
#     rank = self.sqlalchemy_session.query(User.rank).filter(User.id == user_id).scalar()
#     return rank
