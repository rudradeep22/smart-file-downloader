import unittest
from unittest.mock import MagicMock, patch, Mock
import urllib.robotparser
from file_scraper import can_fetch, setup_robot_parser

class TestRobotsGitHub(unittest.TestCase):
    """Test robots.txt functionality specifically with GitHub"""
    
    def test_can_fetch_with_parser_allowed(self):
        """Test can_fetch returns True when robots.txt allows"""
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = True
        
        result = can_fetch(mock_parser, 'https://github.com/user/repo')
        
        self.assertTrue(result)
        mock_parser.can_fetch.assert_called_once_with("*", 'https://github.com/user/repo')
    
    def test_can_fetch_with_parser_disallowed(self):
        """Test can_fetch returns False when robots.txt disallows"""
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = False
        
        result = can_fetch(mock_parser, 'https://github.com/search')
        
        self.assertFalse(result)
        mock_parser.can_fetch.assert_called_once_with("*", 'https://github.com/search')
    
    def test_can_fetch_with_none_parser(self):
        """Test can_fetch returns True when no parser provided"""
        result = can_fetch(None, 'https://github.com/user/repo')
        self.assertTrue(result)
    
    def test_github_robots_url_construction(self):
        """Test correct robots.txt URL construction for GitHub"""
        with patch('file_scraper.urllib.robotparser.RobotFileParser') as mock_parser_class:
            mock_instance = MagicMock()
            mock_parser_class.return_value = mock_instance
            
            result = setup_robot_parser('https://github.com/user/repo')
            
            # Verify correct setup calls
            mock_parser_class.assert_called_once()
            mock_instance.set_url.assert_called_once_with('https://github.com/robots.txt')
            mock_instance.read.assert_called_once()
            self.assertEqual(result, mock_instance)
    
    # Mocked tests based on GitHub's expected robots.txt behavior
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_pulse_urls(self, mock_setup):
        """Test that pulse URLs are disallowed (/*/*/pulse)"""
        mock_parser = MagicMock()
        # Simulate GitHub's robots.txt behavior
        def mock_can_fetch(user_agent, url):
            if '/pulse' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test pulse URLs (should be disallowed per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo/pulse'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/microsoft/vscode/pulse'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_projects_urls(self, mock_setup):
        """Test that projects URLs are disallowed (/*/*/projects)"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            if '/projects' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test projects URLs (should be disallowed per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo/projects'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/microsoft/vscode/projects'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_search_urls(self, mock_setup):
        """Test that search URLs are disallowed"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            if '/search' in url or 'q=' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test search URLs (should be disallowed per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/search'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/search/advanced'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/search?q=python'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_archive_urls(self, mock_setup):
        """Test that archive URLs are disallowed (/*/archive/)"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            if '/archive/' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test archive URLs (should be disallowed per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo/archive/main.zip'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/microsoft/vscode/archive/refs/heads/main.tar.gz'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_gist_urls(self, mock_setup):
        """Test that gist URLs are disallowed (/gist/)"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            if '/gist/' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test gist URLs (should be disallowed per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/gist/123456'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/gist/abcdef123456'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_disallowed_query_params(self, mock_setup):
        """Test that URLs with disallowed query parameters are blocked"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            disallowed_params = ['source=', 'ref_cta=', 'plan=', 'return_to=', 'tab=']
            for param in disallowed_params:
                if param in url and 'tab=achievements' not in url:
                    return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test URLs with disallowed query parameters (per robots.txt)
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo?source=homepage'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo?ref_cta=button'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo?plan=free'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo?return_to=dashboard'))
        self.assertFalse(can_fetch(mock_parser, 'https://github.com/user/repo?tab=repositories'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_allowed_tab_achievements(self, mock_setup):
        """Test that tab=achievements URLs are allowed (exception to tab= rule)"""
        mock_parser = MagicMock()
        def mock_can_fetch(user_agent, url):
            if 'tab=achievements' in url:
                return True
            elif 'tab=' in url:
                return False
            return True
        
        mock_parser.can_fetch.side_effect = mock_can_fetch
        mock_setup.return_value = mock_parser
        
        # Test tab=achievements URLs (should be allowed as exception per robots.txt)
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/user?tab=achievements&achievement=quickdraw'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/user?tab=achievements&achievement=pullshark'))
    
    @patch('file_scraper.setup_robot_parser')
    def test_github_allowed_basic_repo_urls(self, mock_setup):
        """Test that basic repository URLs are allowed"""
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = True  # Basic URLs are allowed
        mock_setup.return_value = mock_parser
        
        # Test basic repo URLs (should be allowed - not in disallow list)
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/microsoft/vscode'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/microsoft/vscode/blob/main/README.md'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/microsoft/vscode/releases'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/microsoft'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/user/repo'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/user/repo/issues'))
        self.assertTrue(can_fetch(mock_parser, 'https://github.com/user/repo/pull/123'))

if __name__ == '__main__':
    unittest.main(verbosity=2)