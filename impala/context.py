# Copyright 2014 Cloudera Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

from six import reraise

from impala.util import _random_id
from impala.dbapi import connect


class ImpalaContext(object):

    def __init__(self, temp_dir=None, temp_db=None, nn_host=None,
                 webhdfs_port=50070, hdfs_user=None, *args, **kwargs):
        # args and kwargs get passed directly into impala.dbapi.connect()
        suffix = _random_id(length=8)
        self._temp_dir = '/tmp/impyla-%s' % (
            suffix if temp_dir is None else temp_dir)
        self._temp_db = 'tmp_impyla_%s' % (
            suffix if temp_db is None else temp_db)
        self._conn = connect(*args, **kwargs)
        self._cursor = self._conn.cursor()
        # used for pywebhdfs cleanup of temp dir; not required
        self._nn_host = nn_host
        self._webhdfs_port = webhdfs_port
        self._hdfs_user = hdfs_user
        if temp_db is None:
            self._cursor.execute("CREATE DATABASE %s LOCATION '%s'" %
                                 (self._temp_db, self._temp_dir))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        if exc_type is not None:
            reraise(exc_type, exc_value, traceback)

    def close(self):
        # drop the temp database
        self._cursor.execute('USE %s' % self._temp_db)
        self._cursor.execute('SHOW TABLES')
        temp_tables = [x[0] for x in self._cursor.fetchall()]
        for table in temp_tables:
            self._cursor.execute(
                'DROP TABLE IF EXISTS %s.%s' % (self._temp_db, table))
        self._cursor.execute('SHOW FUNCTIONS')
        temp_udfs = [x[1] for x in self._cursor.fetchall()]
        for udf in temp_udfs:
            self._cursor.execute(
                'DROP FUNCTION IF EXISTS %s.%s' % (self._temp_db, udf))
        self._cursor.execute('SHOW AGGREGATE FUNCTIONS')
        temp_udas = [x[1] for x in self._cursor.fetchall()]
        for uda in temp_udas:
            self._cursor.execute(
                'DROP AGGREGATE FUNCTION IF EXISTS %s.%s' % (
                    self._temp_db, uda))
        self._cursor.execute('USE default')
        self._cursor.execute('DROP DATABASE IF EXISTS %s' % self._temp_db)
        # drop the temp dir in HDFS
        try:
            from requests.exceptions import ConnectionError
            hdfs_client = self.hdfs_client()
            hdfs_client.delete_file_dir(self._temp_dir.lstrip('/'),
                                        recursive=True)
        except ImportError:
            import sys
            sys.stderr.write("Could not import requests or pywebhdfs. "
                             "You must delete the temporary directory "
                             "manually: %s" % self._temp_dir)
        except ConnectionError:
            import sys
            sys.stderr.write("Could not connect via pywebhdfs. "
                             "You must delete the temporary directory "
                             "manually: %s" % self._temp_dir)

    def hdfs_client(self):
        from pywebhdfs.webhdfs import PyWebHdfsClient
        return PyWebHdfsClient(
            host=self._nn_host, port=self._webhdfs_port,
            user_name=self._hdfs_user)
