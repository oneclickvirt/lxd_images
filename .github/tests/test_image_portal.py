import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('portal',Path(__file__).resolve().parents[1]/'scripts/style_image_portal.py')
portal=importlib.util.module_from_spec(spec);spec.loader.exec_module(portal)

class PortalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'streams/v1').mkdir(parents=True)
        self.meta=b'metadata';self.fs=b'rootfs';(self.root/'metadata.xz').write_bytes(self.meta);(self.root/'rootfs.squashfs').write_bytes(self.fs)
        self.items={name:{'ftype':kind,'path':path,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,kind,path,data in
                    [('incus.tar.xz','incus.tar.xz','metadata.xz',self.meta),('rootfs.squashfs','squashfs','rootfs.squashfs',self.fs)]}
        self.product={'os':'Debian','release':'13','arch':'amd64','variant':'cloud','aliases':'debian/13/cloud','versions':{'20240101_0000':{'items':self.items}}}
    def tearDown(self):self.temp.cleanup()
    def save(self):
        (self.root/'streams/v1/spiritlhl.json').write_text(json.dumps({'format':'products:1.0','products':{'debian':self.product}}))
    def test_latest_actual_build_controls_age_not_deployment_time(self):
        self.save();self.assertTrue(portal.models(self.root,'incus')[0]['stale'])
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M')
        self.product['versions'][stamp]={'items':self.items};self.save()
        self.assertFalse(portal.models(self.root,'incus')[0]['stale'])
    def test_damaged_asset_and_path_traversal_prevent_deployment(self):
        self.save();(self.root/'rootfs.squashfs').write_bytes(b'corruption')
        with self.assertRaises(ValueError):portal.models(self.root,'incus')
        self.items['rootfs.squashfs']['path']='../private.txt';self.save()
        with self.assertRaisesRegex(ValueError,'asset path'):portal.models(self.root,'incus')
    def test_model_markup_is_escaped_and_command_matches_platform(self):
        self.product['os']='<img src=x onerror=alert(1)>';self.save()
        page=portal.render(portal.models(self.root,'incus'),'incus')
        self.assertNotIn('<img src=x',page);self.assertIn('&lt;img src=x',page)
        self.assertIn('incus remote add spiritlhl https://incusimages.spiritlhl.net',page)
        self.assertNotIn('lxdimages.spiritlhl.net --protocol',page)
    def test_compact_portal_layout_has_desktop_and_mobile_rules(self):
        self.save()
        page=portal.render(portal.models(self.root,'incus'),'incus')
        self.assertIn('--accent:#176b55',page)
        self.assertIn('@media(max-width:860px)',page)
        self.assertIn('@media(max-width:520px)',page)
        self.assertIn('letter-spacing:0',page)
