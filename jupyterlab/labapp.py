# coding: utf-8
"""A tornado based Jupyter lab server."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os
from tornado import web

from notebook.notebookapp import NotebookApp
from traitlets import Unicode
from notebook.base.handlers import IPythonHandler, FileFindHandler
from jinja2 import FileSystemLoader
from notebook.utils import url_path_join as ujoin
from jupyter_core.paths import jupyter_path

from ._version import __version__
from .labextensions import (
    find_labextension, validate_labextension_folder,
    get_labextension_manifest_data_by_name,
    get_labextension_manifest_data_by_folder,
    get_labextension_config_python, CONFIG_SECTION
)

#-----------------------------------------------------------------------------
# Module globals
#-----------------------------------------------------------------------------

DEV_NOTE_NPM = """It looks like you're running JupyterLab from source.
If you're working on the TypeScript sources of JupyterLab, try running

    npm run watch

from the JupyterLab repo directory in another terminal window to have the
system incrementally watch and build JupyterLab's TypeScript for you, as you
make changes.
"""

HERE = os.path.dirname(__file__)
FILE_LOADER = FileSystemLoader(HERE)
BUILT_FILES = os.path.join(HERE, 'build')
PREFIX = '/lab'
EXTENSION_PREFIX = '/labextension'


class LabHandler(IPythonHandler):
    """Render the Jupyter Lab View."""

    def initialize(self, labextensions):
        self.labextensions = labextensions

    @web.authenticated
    def get(self):
        static_prefix = ujoin(self.base_url, PREFIX)
        labextensions = self.labextensions
        data = get_labextension_manifest_data_by_folder(BUILT_FILES)
        if 'main' not in data:
            msg = ('JupyterLab build artifacts not detected, please see ' + 
                   'CONTRIBUTING.md for build instructions.')
            self.log.error(msg)
            self.write(self.render_template('error.html', 
                       status_code=500, 
                       status_message='JupyterLab Error',
                       page_title='JupyterLab Error',
                       message=msg))
            return

        main = data['main']['entry']
        bundles = [ujoin(static_prefix, name + '.bundle.js') for name in
                   ['loader', 'main']]
        entries = []

        # Only load CSS files if they exist.
        css_files = []
        for css_file in ['main.css']:
            if os.path.isfile(os.path.join(BUILT_FILES, css_file)):
                css_files.append(ujoin(static_prefix, css_file))

        config = dict(
            static_prefix=static_prefix,
            page_title='JupyterLab Alpha Preview',
            mathjax_url=self.mathjax_url,
            jupyterlab_main=main,
            jupyterlab_css=css_files,
            jupyterlab_bundles=bundles,
            plugin_entries=entries,
            mathjax_config='TeX-AMS_HTML-full,Safe',
            #mathjax_config=self.mathjax_config # for the next release of the notebook
        )

        configData = dict(
            terminalsAvailable=self.settings.get('terminals_available', False),
        )
        extension_prefix = ujoin(self.base_url, EXTENSION_PREFIX)

        # Gather the lab extension files and entry points.
        for (name, data) in sorted(labextensions.items()):
            for value in data.values():
                if not isinstance(value, dict):
                    continue
                if value.get('entry', None):
                    entries.append(value['entry'])
                    bundles.append('%s/%s/%s' % (
                        extension_prefix, name, value['files'][0]
                    ))
                for fname in value['files']:
                    if os.path.splitext(fname)[1] == '.css':
                        css_files.append('%s/%s/%s' % (
                            extension_prefix, name, fname
                        ))
            python_module = data.get('python_module', None)
            if python_module:
                try:
                    value = get_labextension_config_python(python_module)
                    configData.update(value)
                except Exception as e:
                    self.log.error(e)

        config['jupyterlab_config'] = configData
        self.write(self.render_template('lab.html', **config))

    def get_template(self, name):
        return FILE_LOADER.load(self.settings['jinja2_env'], name)



def load_jupyter_server_extension(nbapp):
    """Load the JupyterLab server extension.
    """
    # Print messages.
    nbapp.log.info('JupyterLab alpha preview extension loaded from %s' % HERE)
    base_dir = os.path.realpath(os.path.join(HERE, '..'))
    dev_mode = os.path.exists(os.path.join(base_dir, '.git'))
    if dev_mode:
        nbapp.log.info(DEV_NOTE_NPM)

    # Get the appropriate lab config.
    lab_config = nbapp.config.get(CONFIG_SECTION, {})
    web_app = nbapp.web_app

    # Add the lab extensions to the web app.
    out = dict()
    for (name, ext_config) in lab_config.labextensions.items():
        if not ext_config['enabled']:
            continue
        folder = find_labextension(name)
        if folder is None:
            continue
        warnings = validate_labextension_folder(name, folder)
        if warnings:
            continue
        data = get_labextension_manifest_data_by_name(name)
        if data is None:
            continue
        data['python_module'] = ext_config.get('python_module', None)
        out[name] = data

    # Add the handlers to the web app
    default_handlers = [
        (PREFIX + r'/?', LabHandler, {
            'labextensions': out
        }),
        (PREFIX + r"/(.*)", FileFindHandler,
            {'path': BUILT_FILES}),
    ]
    base_url = web_app.settings['base_url']
    web_app.add_handlers(".*$",
        [(ujoin(base_url, h[0]),) + h[1:] for h in default_handlers])
    extension_prefix = ujoin(base_url, EXTENSION_PREFIX)
    labextension_handler = (
        r"%s/(.*)" % extension_prefix, FileFindHandler, {
            'path': jupyter_path('labextensions'),
            'no_cache_paths': ['/'],  # don't cache anything in labbextensions
        }
    )
    web_app.add_handlers(".*$", [labextension_handler])


class LabApp(NotebookApp):
    version = __version__

    description = """
        JupyterLab - An extensible computational environment for Jupyter.

        This launches a Tornado based HTML Server that serves up an
        HTML5/Javascript JupyterLab client.
    """

    examples = """
        jupyter lab                       # start JupyterLab
        jupyter lab --certfile=mycert.pem # use SSL/TLS certificate
    """

    subcommands = dict()

    default_url = Unicode('/lab', config=True,
        help="The default URL to redirect to from `/`")


#-----------------------------------------------------------------------------
# Main entry point
#-----------------------------------------------------------------------------

main = launch_new_instance = LabApp.launch_instance
