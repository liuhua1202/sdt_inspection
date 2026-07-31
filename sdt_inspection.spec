# PyInstaller spec for SDT Network Device Inspection

# Run with:  python -m PyInstaller sdt_inspection.spec

#
# Output:  dist/sdt_inspection/sdt_inspection.exe + dist/sdt_inspection/_internal/
#
# Layout:  onedir (NOT onefile) -- onedir is required to work around
# PyInstaller 6.21.0 + Python 3.14 Failed to import encodings module bug.
# The PKG archive in onefile mode hides the encodings package from the
# bootloader; onedir keeps the modules as a normal directory tree so
# Python can import them on startup.
#
# Distribution:  zip the entire dist/sdt_inspection/ folder.  The
# end user unzips, drops their devices.csv into the auto-created
# config/ directory (created on first launch), and runs the .exe.
#
# Runtime behaviour:
#   * logs/   ->  dist/sdt_inspection/InspectionLogs/
#   * config/ ->  dist/sdt_inspection/config/  (seeded on first
#                 launch with a sample devices.csv + README.txt)

# -*- mode: python ; coding: utf-8 -*-



import sys

import os



# Spec file is run as a script, so its path is sys.argv[0]

SPEC_FILE = os.path.abspath(sys.argv[0])

PROJECT_ROOT = os.path.dirname(SPEC_FILE)



PATHS = [PROJECT_ROOT]



# Hidden imports: paramiko + netmiko dynamically load many submodules

HIDDEN_IMPORTS = [

    'sdt_app',

    'sdt_app.config_loader',

    'sdt_app.inspection_service',

    'sdt_app.logging_service',

    'sdt_app.models',

    'sdt_app.output',

    'sdt_app.paths',

    'sdt_app.scheduler',

    'sdt_app.transport',

    'sdt_app.ui',

    'sdt_app.widgets',

    'sdt_app.messages',

    'paramiko',

    'paramiko.transport',

    'paramiko.client',

    'paramiko.ssh_exception',

    'paramiko.config',

    'paramiko.util',

    'paramiko.ed25519key',

    'paramiko.ecdsakey',

    'paramiko.dsskey',

    'paramiko.rsakey',

    'paramiko.ed25519',

    'paramiko.pyasn1',

    'paramiko.pyasn1.type',

    'paramiko.pyasn1.type.univ',

    'paramiko.pyasn1.type.namedtype',

    'paramiko.pyasn1.codec.ber',

    'bcrypt',

    'nacl',

    'nacl.bindings',

    'nacl.signing',

    'nacl.exceptions',

    'netmiko',

    'netmiko.ssh_dispatcher',

    'netmiko.base_connection',

    'netmiko.cisco',

    'netmiko.cisco_ios',

    'netmiko.huawei',

    'netmiko.h3c',

    'netmiko.ruijie',

    'netmiko.platform',

    'netmiko.utilities',

    'netmiko.exceptions',

    'netmiko.linux',

    'netmiko.terminal_server',

    'netmiko.terminal_server_telnet',

    'netmiko.terminal_server_generic',

    'serial',

    'serial.serialutil',

    'serial.serialcli',

    'PIL',

    'PIL.Image',

    'PIL.ImageTk',

    'PIL.ImageDraw',

    'cryptography',

    'cryptography.fernet',

    'concurrent.futures',

    'concurrent.futures.thread',

    'concurrent.futures',

    # Workaround for PyInstaller 6.21.0 / Python 3.14 `encodings` bug

    'encodings',

    'encodings.aliases',

    'encodings.ascii',

    'encodings.base64_codec',

    'encodings.big5',

    'encodings.big5hkscs',

    'encodings.bz2_codec',

    'encodings.charmap',

    'encodings.cp037',

    'encodings.cp1006',

    'encodings.cp1026',

    'encodings.cp1125',

    'encodings.cp1140',

    'encodings.cp1252',

    'encodings.cp1253',

    'encodings.cp1254',

    'encodings.cp1255',

    'encodings.cp1256',

    'encodings.cp1257',

    'encodings.cp1258',

    'encodings.cp273',

    'encodings.cp424',

    'encodings.cp437',

    'encodings.cp500',

    'encodings.cp720',

    'encodings.cp737',

    'encodings.cp775',

    'encodings.cp850',

    'encodings.cp852',

    'encodings.cp855',

    'encodings.cp856',

    'encodings.cp857',

    'encodings.cp858',

    'encodings.cp860',

    'encodings.cp861',

    'encodings.cp862',

    'encodings.cp863',

    'encodings.cp864',

    'encodings.cp865',

    'encodings.cp866',

    'encodings.cp869',

    'encodings.cp874',

    'encodings.cp875',

    'encodings.cp932',

    'encodings.cp949',

    'encodings.cp950',

    'encodings.cp1006',

    'encodings.cp1026',

    'encodings.cp1140',

    'encodings.cp1250',

    'encodings.cp1251',

    'encodings.cp1252',

    'encodings.cp1253',

    'encodings.cp1254',

    'encodings.cp1255',

    'encodings.cp1256',

    'encodings.cp1257',

    'encodings.cp1258',

    'encodings.cp273',

    'encodings.cp424',

    'encodings.cp437',

    'encodings.cp500',

    'encodings.cp720',

    'encodings.cp737',

    'encodings.cp775',

    'encodings.cp850',

    'encodings.cp852',

    'encodings.cp855',

    'encodings.cp856',

    'encodings.cp857',

    'encodings.cp858',

    'encodings.cp860',

    'encodings.cp861',

    'encodings.cp862',

    'encodings.cp863',

    'encodings.cp864',

    'encodings.cp865',

    'encodings.cp866',

    'encodings.cp869',

    'encodings.cp874',

    'encodings.cp875',

    'encodings.cp932',

    'encodings.cp949',

    'encodings.cp950',

    'encodings.euc_jisx0213',

    'encodings.euc_jis_2004',

    'encodings.euc_jp',

    'encodings.euc_kr',

    'encodings.gb18030',

    'encodings.gb2312',

    'encodings.gbk',

    'encodings.hex_codec',

    'encodings.hp_roman8',

    'encodings.hz',

    'encodings.idna',

    'encodings.iso2022_jp',

    'encodings.iso2022_jp_1',

    'encodings.iso2022_jp_2',

    'encodings.iso2022_jp_2004',

    'encodings.iso2022_jp_3',

    'encodings.iso2022_jp_ext',

    'encodings.iso2022_kr',

    'encodings.iso8859_1',

    'encodings.iso8859_10',

    'encodings.iso8859_11',

    'encodings.iso8859_13',

    'encodings.iso8859_14',

    'encodings.iso8859_15',

    'encodings.iso8859_16',

    'encodings.iso8859_2',

    'encodings.iso8859_3',

    'encodings.iso8859_4',

    'encodings.iso8859_5',

    'encodings.iso8859_6',

    'encodings.iso8859_7',

    'encodings.iso8859_8',

    'encodings.iso8859_9',

    'encodings.johab',

    'encodings.koi8_r',

    'encodings.koi8_t',

    'encodings.koi8_u',

    'encodings.kz1048',

    'encodings.latin_1',

    'encodings.mac_arabic',

    'encodings.mac_centeuro',

    'encodings.mac_croatian',

    'encodings.mac_cyrillic',

    'encodings.mac_farsi',

    'encodings.mac_greek',

    'encodings.mac_iceland',

    'encodings.mac_latin2',

    'encodings.mac_roman',

    'encodings.mac_romanian',

    'encodings.mac_turkish',

    'encodings.mbcs',

    'encodings.mocha_tokenize',

    'encodings.palmos',

    'encodings.ptcp154',

    'encodings.punycode',

    'encodings.quopri_codec',

    'encodings.raw_unicode_escape',

    'encodings.rot_13',

    'encodings.shift_jis',

    'encodings.shift_jis_2004',

    'encodings.shift_jisx0213',

    'encodings.tis_620',

    'encodings.undefined',

    'encodings.unicode_escape',

    'encodings.unicode_internal',

    'encodings.utf_16',

    'encodings.utf_16_be',

    'encodings.utf_16_le',

    'encodings.utf_7',

    'encodings.utf_8',

    'encodings.utf_8_sig',

    'encodings.uu_codec',

    'encodings.zlib_codec',

    'encodings.cp65001',



]



# Data files bundled with the exe.

# Only the favicon is embedded.  Config/ is seeded at runtime

# by sdt_app.paths._seed_config_template so the operator's own

# devices.csv lives next to the .exe (writable, easy to back up)

# and is never overwritten by re-installing the app.

# Format: (source_absolute, destination_relative_inside_bundle)

FAVICON = os.path.join(PROJECT_ROOT, 'favicon.ico')

DATA = [

    (FAVICON, '.'),  # place favicon.ico at _internal/favicon.ico directly

]

a = Analysis(

    ['sdt_inspection_v1.0.1.py'],

    pathex=PATHS,

    binaries=[],

    datas=DATA,

    hiddenimports=HIDDEN_IMPORTS,

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[

        'tkinter.test',

        'test',

        'unittest',

        'pydoc',

        'doctest',

    ],

    noarchive=False,

)



pyz = PYZ(a.pure, a.zipped_data, cipher=None)



# onedir layout (workaround for PyInstaller 6.21.0 + Python 3.14

# Failed to import encodings bug).  Modules stay as files instead

# of being packed into a PKG archive the bootloader cannot open.

# Output: dist/sdt_inspection/sdt_inspection.exe + _internal/ folder.

exe = EXE(

    pyz,

    a.scripts,

    [],

    [],

    exclude_binaries=True,

    name='sdt_inspection',

    debug=False,

    bootloader_ignore_signals=False,

    strip=False,

    upx=False,

    console=False,

    disable_windowed_traceback=False,

    argv_emulation=False,

    target_arch=None,

    codesign_identity=None,

    entitlements_file=None,

    icon=FAVICON,

)



coll = COLLECT(

    exe,

    a.binaries,

    a.zipfiles,

    a.datas,

    strip=False,

    upx=False,

    upx_exclude=[],

    name='sdt_inspection',

)

