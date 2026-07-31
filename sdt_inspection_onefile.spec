# PyInstaller spec for the SDT Network Device Inspection tool,
# SINGLE-FILE build (onefile).
#
# Run with:  python -m PyInstaller sdt_inspection_onefile.spec
#
# Output:  dist/sdt_inspection_onefile.exe  (a single executable;
# the bootloader extracts _internal to %TEMP% at runtime).
#
# The onedir build in sdt_inspection.spec is the safer default for
# Python 3.14 (the bootloader in onefile mode has historically
# hidden the `encodings` package from the interpreter; onedir keeps
# the modules as a normal directory tree).  This spec exists for
# operators who prefer a single-file distribution and accept the
# risk that they may need to switch back to onedir on certain
# Python / PyInstaller combinations.
#
# Runtime behaviour:
#   * logs/   ->  <exe directory>/InspectionLogs/
#   * config/ ->  <exe directory>/config/  (seeded on first
#                 launch with a sample devices.csv + README.txt)
#
# Distribution:  hand the single .exe to the end user, or zip it.
# There is no _internal/ folder to keep alongside.

# -*- mode: python ; coding: utf-8 -*-


import sys

import os


# Spec file is run as a script, so its path is sys.argv[0]

SPEC_FILE = os.path.abspath(sys.argv[0])

PROJECT_ROOT = os.path.dirname(SPEC_FILE)



PATHS = [PROJECT_ROOT]



# Hidden imports: paramiko + netmiko dynamically load many submodules.
# Same list as the onedir spec so the two builds stay in lock-step.

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

    # Workaround for the PyInstaller + Python 3.14
    # "Failed to import encodings" class of bugs.  Listing
    # them explicitly here forces PyInstaller to keep them
    # in the PYZ archive; without this the bootloader in
    # onefile mode has been observed to hide them.

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

    'encodings.cp65001',

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

]



# Data files bundled with the exe.

FAVICON = os.path.join(PROJECT_ROOT, 'favicon.ico')

DATA = [

    (FAVICON, '.'),

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



# onefile:  every binary, zipfile, and data file is packed
# into the single EXE; the bootloader extracts them to %TEMP%
# at startup.  No COLLECT step.
exe = EXE(

    pyz,

    a.scripts,

    a.binaries,

    a.zipfiles,

    a.datas,

    [],

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
