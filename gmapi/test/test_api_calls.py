#!/usr/bin/env python

#Copyright 2012 Simon Weber.

#This file is part of gmapi - the Unofficial Google Music API.

#Gmapi is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#Gmapi is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with gmapi.  If not, see <http://www.gnu.org/licenses/>.

"""A test harness for api features."""


import unittest
import os
import string
import copy
import time


from gmapi.protocol import WC_Protocol
from gmapi.utils.apilogging import LogController
import gmapi.test.utils as test_utils


#Expected to be in this directory.
test_filename = "test.mp3"
    
#Metadata expectations:
limited_md = WC_Protocol.modifyentries.limited_md #should refactor this
mutable_md = WC_Protocol.modifyentries.mutable_md
frozen_md = WC_Protocol.modifyentries.frozen_md
dependent_md = WC_Protocol.modifyentries.dependent_md
server_md = WC_Protocol.modifyentries.server_md


class TestWCApiCalls(test_utils.BaseTest):
    """Runs integration tests for api calls.
    Tests are intended not to modify the library, but no guarantees are made.
    """

    @classmethod
    def setUpClass(cls):
        super(TestWCApiCalls, cls).setUpClass()

        cls.log = LogController().get_logger("gmapi.test.TestWcApiCalls")

        #Get the full path of the test file.
        path = os.path.realpath(__file__)
        cls.test_filename = path[:string.rfind(path, r'/')] + r'/' + test_filename

    #---
    #   Monolithic tests: 
    #   (messy, but less likely to destructively modify the library)
    #   Modified from http://stackoverflow.com/questions/5387299/python-unittest-testcase-execution-order
    #---
        
    def pl_1_create(self):
        """Create a playlist."""
        self.assert_success(
            self.api.create_playlist('test playlist'))

        #Need to reload playlists so it appears.
        self.playlists = self.api.get_playlists()


    def pl_2_add_song(self):
        """Add a random song to the playlist."""
        self.assert_success(
            self.api.add_songs_to_playlist(self.playlists['test playlist'], self.r_song_id))

        #Verify the playlist has it.
        tracks = self.api.get_playlist_songs(self.playlists['test playlist'])

        self.assertTrue(tracks[0]["id"] == self.r_song_id)
        

    def pl_2a_remove_song(self):
        """Remove a song from the playlist."""

        sid = self.api.get_playlist_songs(self.playlists['test playlist'])[0]["id"]
        
        self.assert_success(
            self.api.remove_song_from_playlist(sid, self.playlists['test playlist']))

        #Verify.
        tracks = self.api.get_playlist_songs(self.playlists['test playlist'])

        self.assertTrue(len(tracks) == 0)

    def pl_3_change_name(self):
        """Change the playlist's name."""
        self.assert_success(
            self.api.change_playlist_name(self.playlists['test playlist'], 'modified playlist'))

        self.playlists = self.api.get_playlists()
            
    def pl_4_delete(self):
        """Delete the playlist."""
        self.assert_success(
            self.api.delete_playlist(self.playlists['modified playlist']))

        self.playlists = self.api.get_playlists()


    def test_playlists(self):
        self.run_steps("pl")


    def updel_1_upload(self):
        """Upload the test file."""
        result = self.api.upload(self.test_filename)
        self.assertTrue(self.test_filename in result)

        #A bit messy; need to pass the id on to the next step.
        self.uploaded_id = result[self.test_filename]

    def updel_2_delete(self):
        """Delete the uploaded test file."""
        self.assert_success(
            self.api.delete_song(self.uploaded_id))

        del self.uploaded_id

    def test_up_deletion(self):
        self.run_steps("updel_")

        

    #---
    #   Non-monolithic tests:
    #---

    #Works, but the protocol isn't mature enough to support the call (yet).
    # def test_get_song_download_info(self):
    #     #The api doesn't expose the actual response here,
    #     # instead we expect a tuple with 2 entries.
    #     res = self.api.get_song_download_info(self.r_song_id)
    #     self.assertTrue(len(res) == 2 and isinstance(res, tuple))
            

    def test_change_song_metadata(self):
        """Change a song's metadata, then restore it."""
        #Get a random song's metadata.
        orig_md = [s for s in self.library if s["id"] == self.r_song_id][0]
        self.log.debug("original md: %s", repr(orig_md))

        #Generate noticably changed metadata for ones we can change.
        new_md = copy.deepcopy(orig_md)
        for key in mutable_md:
            if key in orig_md:
                old_val = orig_md[key]
                new_val = test_utils.modify_md(key, old_val)

                self.log.debug("%s: %s modified to %s", key, repr(old_val), repr(new_val))
                self.assertTrue(new_val != old_val)
                new_md[key] = new_val
                            
        
        #Make the call to change the metadata.
        #This should succeed, even though we _shouldn't_ be able to change some entries.
        #The call only fails if you give the wrong datatype.
        self.assert_success(
            self.api.change_song_metadata(new_md))

        #Refresh the library to flush the changes, then find the song.
        #Assume the id won't change (testing has shown this to be true).
        time.sleep(3)
        self.library = self.api.get_all_songs()
        result_md = [s for s in self.library if s["id"] == orig_md["id"]][0]
        
        self.log.debug("result md: %s", repr(result_md))

        #Verify everything went as expected:
        # things that should change did
        for md_name in mutable_md:
            if md_name in orig_md: #some songs are missing entries (eg albumArtUrl)
                truth, message = test_utils.md_entry_same(md_name, orig_md, result_md)
                self.assertTrue(not truth, "should not equal " + message)

        # things that shouldn't change didn't
        for md_name in frozen_md:
            if md_name in orig_md:
                truth, message = test_utils.md_entry_same(md_name, orig_md, result_md)
                self.assertTrue(truth, "should equal " + message)

        #Recreate the dependent md to what they should be (based on how orig_md was changed)
        correct_dependent_md = {}
        for dep_key in dependent_md:
            if dep_key in orig_md:
                master_key, trans = dependent_md[dep_key]
                correct_dependent_md[dep_key] = trans(new_md[master_key])
                self.log.debug("dependents (%s): %s -> %s", dep_key, new_md[master_key], correct_dependent_md[dep_key])

        #Make sure dependent md is correct.
        for dep_key in correct_dependent_md:
            truth, message = test_utils.md_entry_same(dep_key, correct_dependent_md, result_md)
            self.assertTrue(truth, "should equal: " + message)

            
        #Revert the metadata.
        self.assert_success(
            self.api.change_song_metadata(orig_md))

        #Verify everything is as it was.
        time.sleep(3)
        self.library = self.api.get_all_songs()
        result_md = [s for s in self.library if s["id"] == orig_md["id"]][0]

        self.log.debug("result md: %s", repr(result_md))

        for md_name in orig_md:
            if md_name not in server_md: #server md _can_ change
                truth, message = test_utils.md_entry_same(md_name, orig_md, result_md)
                self.assertTrue(truth, "should equal: " + message)
        

    def test_search(self):
        self.assert_success(
            self.api.search('e'))

    def test_get_stream_url(self):
        #This should return a valid url.
        #This is not robust; it's assumed that invalid calls will raise an error before this point.
        url = self.api.get_stream_url(self.r_song_id)
        self.assertTrue(url[:4] == "http")
        

if __name__ == '__main__':
    unittest.main()
