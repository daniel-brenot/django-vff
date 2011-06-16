# Copyright 2011 Terena. All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:

#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.

#    2. Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#        and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY TERENA ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL TERENA OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of Terena.

import os
import re
import git
from git.config import GitConfigParser
from types import MethodType
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.core.files.move import file_move_safe

from vff.abcs import VFFBackend

USERPAT = re.compile(ur'^([^<]+) <(.+)>$')
EMAILPAT = re.compile(ur'^([^@]+)@.+$')

GITCONFIG = u'''\
[user]
 name = %s
 email = %s
'''

def clean_environment():
    for env in ('USER', 'USERNAME',
            'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL',
            'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL',
            'GIT_AUTHOR_DATE', 'GIT_COMMITER_DATE'):
        if env in os.environ:
            del os.environ[env]


class Repo(git.Repo):
    """
    This class is only to get rid of the __slots__
    nuisance in the original class, whereupon you cannot
    override instance methods.
    """


class GitBackend(object):
    """
    Git backend for versioned file field's storage.
    See abcs.py for documentation.
    """

    def __init__(self, location):
        self.location = location
        try:
            self.repo = Repo(self.location)
        except git.exc.NoSuchPathError:
            self.repo = Repo.init(self.location)

    def _commit(self, fname, msg, username):
        mu = USERPAT.match(username)
        me = EMAILPAT.match(username)
        if mu:
            config = GITCONFIG % (mu.group(1), mu.group(2))
        elif me:
            config = GITCONFIG % (me.group(1), me.group(0))
        else:
            config = GITCONFIG % (username, username)
        with NamedTemporaryFile(delete=True) as f:
            f.write(config.encode('utf8'))
            f.seek(0)
            def fun(self, config_level=None):
                return f
            meth = MethodType(fun, self.repo, Repo)
            setattr(self.repo, '_get_config_path', meth)
            setattr(self.repo, 'config_level', ['repository'])
            clean_environment()
            self.repo.index.add([fname])
            self.repo.index.commit(msg)

    def add_revision(self, content, fname, commit_msg, username):
        full_path = os.path.join(self.location, fname)
        if hasattr(content, 'temporary_file_path'):
            # This file has a file path that we can move.
            file_move_safe(content.temporary_file_path(), full_path)
            content.close()
        else:
            # This is a normal uploadedfile that we can stream.
            with open(full_path, 'w') as f:
                content.seek(0)
                f.write(content.read())
        if settings.FILE_UPLOAD_PERMISSIONS is not None:
            os.chmod(full_path, settings.FILE_UPLOAD_PERMISSIONS)
        self._commit(fname, commit_msg, username)

    def get_revision(self, fname, rev=None):
        full_path = os.path.join(self.location, fname)
        text = u''
        if rev:
            pass  # XXX check out revision. Set a lock?
        if os.path.exists(full_path):
            with open(full_path) as f:
                text = f.read()
        # XXX undo check out
        return text

    def del_document(self, fname, commit_msg):
        self.repo.remove([fname])
        self.repo.index.commit(commit_msg)

    def list_revisions(self, fname, count=0, offset=0):
        revs = []
        for ci in self.repo.iter_commits(paths=fname,
                                         max_count=count,
                                         skip=offset):
            revs.append((ci.hexsha, ci.committed_date, ci.message))
        return revs
    
    def get_diff(self, fname, id1, id2):
        ci1 = self.repo.commit(id1)
        ci2 = self.repo.commit(id2)
        diff = ci1.diff(other=ci2, paths=fname, create_patch=True)[0]
        return diff.diff

VFFBackend.register(GitBackend)
