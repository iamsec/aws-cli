# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import os
import sys

from awscli.compat import compat_open
from awscli.customizations.utils import uni_print
from awscli.customizations.commands import BasicCommand
from awscli.customizations.configure.writer import ConfigFileWriter


class ConfigureImportCommand(BasicCommand):
    NAME = 'import'
    DESCRIPTION = 'Import CSV credentials generated from the AWS web console.'
    EXAMPLES = (
        'aws configure import --csv file://credentials.csv\n\n'
        'aws configure import --csv file://credentials.csv --skip-invalid\n'
    )
    ARG_TABLE = [
        {'name': 'csv',
         'required': True,
         'help_text': (
             'The credentials in CSV format generated by the AWS web console.'
         ),
         'cli_type_name': 'string'},
        {'name': 'skip-invalid',
         'dest': 'skip_invalid',
         'help_text': (
             'Skip entries that are invalid or do not have programmatic '
             'access instead of failing.'
         ),
         'default': False,
         'action': 'store_true'},
    ]

    def __init__(self, session, csv_parser=None, importer=None,
                 out_stream=None):
        super(ConfigureImportCommand, self).__init__(session)
        if csv_parser is None:
            csv_parser = CSVCredentialParser()
        self._csv_parser = csv_parser

        if importer is None:
            writer = ConfigFileWriter()
            importer = CredentialImporter(writer)
        self._importer = importer

        if out_stream is None:
            out_stream = sys.stdout
        self._out_stream = out_stream

    def _get_config_path(self):
        config_file = self._session.get_config_variable('credentials_file')
        return os.path.expanduser(config_file)

    def _import_csv(self, contents):
        config_path = self._get_config_path()
        credentials = self._csv_parser.parse_credentials(contents)
        for credential in credentials:
            self._importer.import_credential(credential, config_path)
        import_msg = 'Successfully imported %s profile(s)\n' % len(credentials)
        uni_print(import_msg, out_file=self._out_stream)

    def _run_main(self, parsed_args, parsed_globals):
        self._csv_parser.strict = not parsed_args.skip_invalid
        self._import_csv(parsed_args.csv)


class CredentialParserError(Exception):
    pass


class CSVCredentialParser(object):
    _USERNAME_HEADER = 'User Name'
    _AKID_HEADER = 'Access Key ID'
    _SAK_HEADER = 'Secret Access key'
    _EXPECTED_HEADERS = [_USERNAME_HEADER, _AKID_HEADER, _SAK_HEADER]

    _EMPTY_CSV = 'Provided CSV contains no contents'
    _HEADER_NOT_FOUND = 'Expected header "%s" not found'
    _INVALID_USERNAME = 'Failed to parse User Name for entry #%s'
    _INVALID_SECRET = (
        'Failed to parse Access Key ID or Secret Access Key for entry #%s'
    )

    def __init__(self, strict=True):
        self.strict = strict

    def _format_header(self, header):
        return header.lower().strip()

    def _parse_csv_headers(self, header):
        indices = []
        parsed_headers = [self._format_header(h) for h in header.split(',')]

        for header in self._EXPECTED_HEADERS:
            formatted_header = self._format_header(header)
            if formatted_header not in parsed_headers:
                raise CredentialParserError(self._HEADER_NOT_FOUND % header)
            indices.append(parsed_headers.index(formatted_header))

        return indices

    def _parse_csv_rows(self, rows, headers):
        credentials = []
        username_index, akid_index, sak_index = headers

        count = 0
        for user in rows:
            count += 1
            cols = user.split(',')
            username = cols[username_index].strip()
            akid = cols[akid_index].strip()
            sak = cols[sak_index].strip()

            if not username:
                if self.strict:
                    raise CredentialParserError(self._INVALID_USERNAME % count)
                continue
            if not akid or not sak:
                if self.strict:
                    raise CredentialParserError(self._INVALID_SECRET % count)
                continue

            credentials.append((username, akid, sak))

        return credentials

    def _parse_csv(self, csv):
        # Expected format is:
        # User name,Password,Access key ID,Secret access key,Console login link
        # username1,pw,akid,sak,https://console.link
        # username2,pw,akid,sak,https://console.link
        if not csv.strip():
            raise CredentialParserError(self._EMPTY_CSV)

        lines = csv.splitlines()
        parsed_headers = self._parse_csv_headers(lines[0])
        credentials = self._parse_csv_rows(lines[1:], parsed_headers)

        return credentials

    def parse_credentials(self, contents):
        return self._parse_csv(contents)


class CredentialImporter(object):
    def __init__(self, writer):
        self._config_writer = writer

    def import_credential(self, credential, credentials_file):
        name, akid, sak = credential
        config_profile = {
            '__section__': name,
            'aws_access_key_id': akid,
            'aws_secret_access_key': sak,
        }
        self._config_writer.update_config(config_profile, credentials_file)
