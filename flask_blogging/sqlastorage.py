__author__ = 'Gouthaman Balaraman'

import logging
import sqlalchemy as sqla
import datetime
from . import Storage

class SQLAStorage(Storage):
    _db = None
    _logger = logging.getLogger("flask-blogging")

    def __init__(self, db, table_prefix=""):
        self._engine = db.engine
        self._table_prefix = table_prefix
        self._create_all_tables()

    def save_post(self, title, text, user_id, tags, draft=False, post_id=None):
        new_post = post_id is None
        current_datetime = datetime.datetime.utcnow()
        draft = 1 if draft is True else 0
        post_statement = self._post_table.insert() if post_id is None else \
            self._post_table.update().where(self._post_table.c.id == post_id)
        post_statement = post_statement.values(title=title, text=text, post_date=current_datetime,
                                               last_modified_date=current_datetime, draft=draft)

        with self._engine.begin() as conn:
            post_result = conn.execute(post_statement)
            post_id = post_result.inserted_primary_key[0] if post_id is None else post_id
            self._save_tags(tags, post_id, conn)
            self._save_user_post(user_id, post_id, conn)

    def get_post_by_id(self, post_id):
        r = {}
        with self._engine.begin() as conn:
            post_statement = sqla.select([self._post_table]).where(self._post_table.c.id == post_id)
            post_result = conn.execute(post_statement).fetchone()
            if post_result is not None:
                r['post_id'], r['title'], r['text'], r['post_date'], r['last_modified_date'], r['draft'] = post_result
                tag_statement = sqla.select([self._tag_table.c.text]).\
                    where(sqla.and_(self._tag_table.c.id == self._tag_posts_table.c.tag_id,
                                    self._tag_posts_table.c.post_id == post_id)
                          )
                tag_result = conn.execute(tag_statement).fetchall()
                r["tags"] = [t[0] for t in tag_result]
        return r

    def _save_tags(self, tags, post_id, conn):
        tags = self.normalize_tags(tags)
        tag_insert_statement = self._tag_table.insert()

        for tag in tags:
            try:
                tag_insert_statement = tag_insert_statement.values(text=tag)
                result = conn.execute(tag_insert_statement)
                tag_id = result.inserted_primary_key[0]
            except sqla.exc.IntegrityError as e:
                tag_select_statement = sqla.select([self._tag_table]).where(self._tag_table.c.text == tag)
                result = conn.execute(tag_select_statement).fetchone()
                tag_id = result[0]
            try:
                tag_post_statement = self._tag_posts_table.insert().values(tag_id=tag_id, post_id=post_id)
                conn.execute(tag_post_statement)
            except sqla.exc.IntegrityError:
                pass
            except Exception as e:
                self._logger.exception(str(e))

    def _save_user_post(self, user_id, post_id, conn):
        try:
            statement = self._user_posts_table.insert().values(user_id=user_id, post_id=post_id)
            conn.execute(statement)
        except sqla.exc.IntegrityError: # already exists
            pass
        except Exception as e:
            self._logger.exception(str(e))

    def _table_name(self, table_name):
        return self._table_prefix+table_name

    def _create_all_tables(self):
        """
        Creates all the required tables by calling the required functions.
        :return:
        """
        self._create_post_table()
        self._create_tag_table()
        self._create_tag_posts_table()
        self._create_user_posts_table()

    def _create_post_table(self):
        """
        Creates the table to store the blog posts.
        :return:
        """
        with self._engine.begin() as conn:
            metadata = sqla.MetaData()
            post_table_name = self._table_name("post")
            if not conn.dialect.has_table(conn, post_table_name ):
                self._post_table = sqla.Table(
                    post_table_name, metadata,
                    sqla.Column("id", sqla.Integer, primary_key=True),
                    sqla.Column("title", sqla.String(256)),
                    sqla.Column("text", sqla.Text),
                    sqla.Column("post_date", sqla.DateTime),
                    sqla.Column("last_modified_date", sqla.DateTime),
                    sqla.Column("draft", sqla.SmallInteger, default=0)  # if 1 then make it a draft an
                )
                metadata.create_all(self._engine)
                self._logger.debug("Created table with table name %s" % post_table_name)
            else:
                metadata.reflect(bind=self._engine)
                self._post_table = metadata.tables[post_table_name]
                self._logger.debug("Reflecting to table with table name %s" % post_table_name)

    def _create_tag_table(self):
        """
        Creates the table to store blog post tags.
        :return:
        """
        with self._engine.begin() as conn:
            metadata = sqla.MetaData()
            tag_table_name = self._table_name("tag")
            if not conn.dialect.has_table(conn, tag_table_name ):
                self._tag_table = sqla.Table(
                    tag_table_name, metadata,
                    sqla.Column("id", sqla.Integer, primary_key=True),
                    sqla.Column("text", sqla.String(128), unique=True, index=True)
                )
                metadata.create_all(self._engine)
                self._logger.debug("Created table with table name %s" % tag_table_name)
            else:
                metadata.reflect(bind=self._engine)
                self._tag_table = metadata.tables[tag_table_name]
                self._logger.debug("Reflecting to table with table name %s" % tag_table_name)

    def _create_tag_posts_table(self):
        """
        Creates the table to store association info between blog posts and tags.
        :return:
        """
        metadata = sqla.MetaData()
        metadata.reflect(bind=self._engine)
        with self._engine.begin() as conn:
            tag_posts_table_name = self._table_name("tag_posts")
            if not conn.dialect.has_table(conn, tag_posts_table_name ):
                tag_id_key = self._table_name("tag")+".id"
                post_id_key = self._table_name("post")+".id"
                self._tag_posts_table = sqla.Table(
                    tag_posts_table_name, metadata,
                    sqla.Column('tag_id', sqla.Integer,
                                sqla.ForeignKey(tag_id_key, onupdate="CASCADE", ondelete="CASCADE"),
                                index=True),
                    sqla.Column('post_id', sqla.Integer,
                                sqla.ForeignKey(post_id_key, onupdate="CASCADE", ondelete="CASCADE"),
                                index=True),
                    sqla.UniqueConstraint('tag_id', 'post_id', name='uix_1')
                    )
                metadata.create_all(self._engine)
                self._logger.debug("Created table with table name %s" % tag_posts_table_name)
            else:
                self._tag_posts_table = metadata.tables[tag_posts_table_name]
                self._logger.debug("Reflecting to table with table name %s" % tag_posts_table_name)

    def _create_user_posts_table(self):
        """
        Creates the table to store association info between user and blog posts.
        :return:
        """
        metadata = sqla.MetaData()
        metadata.reflect(bind=self._engine)
        with self._engine.begin() as conn:
            user_posts_table_name = self._table_name("user_posts")
            if not conn.dialect.has_table(conn, user_posts_table_name ):
                post_id_key = self._table_name("post")+".id"
                self._user_posts_table = sqla.Table(
                    user_posts_table_name, metadata,
                    sqla.Column("user_id", sqla.String(128), index=True),
                    sqla.Column("post_id", sqla.Integer,
                                sqla.ForeignKey(post_id_key, onupdate="CASCADE", ondelete="CASCADE"),
                                index=True),
                    sqla.UniqueConstraint('user_id', 'post_id', name='uix_2')
                )
                metadata.create_all(self._engine)
                self._logger.debug("Created table with table name %s" % user_posts_table_name)
            else:
                self._user_posts_table = metadata.tables[user_posts_table_name]
                self._logger.debug("Reflecting to table with table name %s" % user_posts_table_name)