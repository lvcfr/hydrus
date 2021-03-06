import ClientConstants as CC
import ClientNetworkingContexts
import ClientParsing
import ClientThreading
import collections
import HydrusConstants as HC
import HydrusGlobals as HG
import HydrusData
import HydrusExceptions
import HydrusNetworking
import HydrusSerialisable
import os
import re
import threading
import time
import urllib
import urlparse

def AlphabetiseQueryText( query_text ):
    
    return ConvertQueryDictToText( ConvertQueryTextToDict( query_text ) )
    
def ConvertDomainIntoAllApplicableDomains( domain, discard_www = True ):
    
    # is an ip address or localhost, possibly with a port
    if '.' not in domain or re.search( r'^[\d\.:]+$', domain ) is not None:
        
        return [ domain ]
        
    
    domains = []
    
    while domain.count( '.' ) > 0:
        
        # let's discard www.blah.com and www2.blah.com so we don't end up tracking it separately to blah.com--there's not much point!
        startswith_www = domain.count( '.' ) > 1 and domain.startswith( 'www' )
        
        should_be_discarded = startswith_www and discard_www
        
        if not should_be_discarded:
            
            domains.append( domain )
            
        
        domain = '.'.join( domain.split( '.' )[1:] ) # i.e. strip off the leftmost subdomain maps.google.com -> google.com
        
    
    return domains
    
def ConvertDomainIntoSecondLevelDomain( domain ):
    
    domains = ConvertDomainIntoAllApplicableDomains( domain )
    
    if len( domains ) == 0:
        
        raise HydrusExceptions.URLMatchException( 'That url or domain did not seem to be valid!' )
        
    
    return domains[-1]
    
def ConvertHTTPSToHTTP( url ):
    
    if url.startswith( 'http://' ):
        
        return url
        
    elif url.startswith( 'https://' ):
        
        http_url = 'http://' + url[8:]
        
        return http_url
        
    else:
        
        raise Exception( 'Given a url that did not have a scheme!' )
        
    
def ConvertHTTPToHTTPS( url ):
    
    if url.startswith( 'https://' ):
        
        return url
        
    elif url.startswith( 'http://' ):
        
        https_url = 'https://' + url[7:]
        
        return https_url
        
    else:
        
        raise Exception( 'Given a url that did not have a scheme!' )
        
    
def ConvertQueryDictToText( query_dict ):
    
    # we now do everything with requests, which does all the unicode -> ascii -> %20 business naturally, phew
    # so lets just stick with unicode, which we still want to call explicitly to coerce integers and so on that'll slip in here and there
    
    param_pairs = list( query_dict.items() )
    
    param_pairs.sort()
    
    query_text = u'&'.join( ( HydrusData.ToUnicode( key ) + u'=' + HydrusData.ToUnicode( value ) for ( key, value ) in param_pairs ) )
    
    return query_text
    
def ConvertQueryTextToDict( query_text ):
    
    # we generally do not want quote characters %20 stuff, in our urls. we would prefer regular ascii and even unicode
    
    # first we will decode all unicode, which allows urllib to work
    query_text = HydrusData.ToByteString( query_text )
    
    query_dict = {}
    
    pairs = query_text.split( '&' )
    
    for pair in pairs:
        
        result = pair.split( '=', 1 )
        
        # for the moment, ignore tracker bugs and so on that have only key and no value
        
        if len( result ) == 2:
            
            # so, let's replace all keys and values with unquoted versions
            # -but-
            # we only replace if it is a completely reversable operation!
            # odd situations like '6+girls+skirt', which comes here encoded as '6%2Bgirls+skirt', shouldn't turn into '6+girls+skirt'
            # so if there are a mix of encoded and non-encoded, we won't touch it here m8
            
            # we convert to unicode afterwards so %E5%B0%BB%E7%A5%9E%E6%A7%98 -> \xe5\xb0\xbb\xe7\xa5\x9e\xe6\xa7\x98 -> \u5c3b\u795e\u69d8
            
            ( key, value ) = result
            
            try:
                
                unquoted_key = urllib.unquote( key )
                
                requoted_key = urllib.quote( unquoted_key )
                
                if key == requoted_key:
                    
                    key = HydrusData.ToUnicode( unquoted_key )
                    
                
            except:
                
                pass
                
            
            try:
                
                unquoted_value = urllib.unquote( value )
                
                requoted_value = urllib.quote( unquoted_value )
                
                if value == requoted_value:
                    
                    value = HydrusData.ToUnicode( unquoted_value )
                    
                
            except:
                
                pass
                
            
            query_dict[ key ] = value
            
        
    
    return query_dict
    
def ConvertURLMatchesIntoAPIPairs( url_matches ):
    
    url_matches = list( url_matches )
    
    NetworkDomainManager.STATICSortURLMatchesDescendingComplexity( url_matches )
    
    pairs = []
    
    for url_match in url_matches:
        
        if not url_match.UsesAPIURL():
            
            continue
            
        
        api_url = url_match.GetAPIURL( url_match.GetExampleURL() )
        
        for other_url_match in url_matches:
            
            if other_url_match == url_match:
                
                continue
                
            
            if other_url_match.Matches( api_url ):
                
                pairs.append( ( url_match, other_url_match ) )
                
                break
                
            
        
    
    return pairs
    
def ConvertURLIntoDomain( url ):
    
    parser_result = urlparse.urlparse( url )
    
    if parser_result.scheme == '':
        
        raise HydrusExceptions.URLMatchException( 'URL "' + url + '" was not recognised--did you forget the http:// or https://?' )
        
    
    if parser_result.netloc == '':
        
        raise HydrusExceptions.URLMatchException( 'URL "' + url + '" was not recognised--is it missing a domain?' )
        
    
    domain = HydrusData.ToByteString( parser_result.netloc )
    
    return domain
    
def ConvertURLIntoSecondLevelDomain( url ):
    
    domain = ConvertURLIntoDomain( url )
    
    return ConvertDomainIntoSecondLevelDomain( domain )
    
def DomainEqualsAnotherForgivingWWW( test_domain, wwwable_domain ):
    
    # domain is either the same or starts with www. or www2. or something
    rule = r'^(www[^\.]*\.)?' + re.escape( wwwable_domain ) + '$'
    
    return re.search( rule, test_domain ) is not None
    
def CookieDomainMatches( cookie, search_domain ):
    
    cookie_domain = cookie.domain
    
    # blah.com is viewable by blah.com
    matches_exactly = cookie_domain == search_domain
    
    # .blah.com is viewable by blah.com
    matches_dot = cookie_domain == '.' + search_domain
    
    # .blah.com applies to subdomain.blah.com, blah.com does not
    valid_subdomain = cookie_domain.startswith( '.' ) and search_domain.endswith( cookie_domain )
    
    return matches_exactly or matches_dot or valid_subdomain
    
def GetCookie( cookies, search_domain, cookie_name_string_match ):
    
    for cookie in cookies:
        
        if CookieDomainMatches( cookie, search_domain ) and cookie_name_string_match.Matches( cookie.name ):
            
            return cookie
            
        
    
    raise HydrusExceptions.DataMissing( 'Cookie "' + cookie_name_string_match.ToUnicode() + '" not found for domain ' + search_domain + '!' )
    
def GetSearchURLs( url ):
    
    search_urls = set()
    
    search_urls.add( url )
    
    normalised_url = HG.client_controller.network_engine.domain_manager.NormaliseURL( url )
    
    search_urls.add( normalised_url )
    
    for url in list( search_urls ):
        
        if url.startswith( 'http://' ):
            
            search_urls.add( ConvertHTTPToHTTPS( url ) )
            
        elif url.startswith( 'https://' ):
            
            search_urls.add( ConvertHTTPSToHTTP( url ) )
            
        
    
    for url in list( search_urls ):
        
        p = urlparse.urlparse( url )
        
        scheme = p.scheme
        netloc = p.netloc
        path = p.path
        params = ''
        query = p.query
        fragment = ''
        
        if netloc.startswith( 'www' ):
            
            try:
                
                netloc = ConvertDomainIntoSecondLevelDomain( netloc )
                
            except HydrusExceptions.URLMatchException:
                
                continue
                
            
        else:
            
            netloc = 'www.' + netloc
            
        
        r = urlparse.ParseResult( scheme, netloc, path, params, query, fragment )
        
        search_urls.add( r.geturl() )
        
    
    return search_urls
    
VALID_DENIED = 0
VALID_APPROVED = 1
VALID_UNKNOWN = 2

valid_str_lookup = {}

valid_str_lookup[ VALID_DENIED ] = 'denied'
valid_str_lookup[ VALID_APPROVED ] = 'approved'
valid_str_lookup[ VALID_UNKNOWN ] = 'unknown'

class NetworkDomainManager( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_DOMAIN_MANAGER
    SERIALISABLE_NAME = 'Domain Manager'
    SERIALISABLE_VERSION = 6
    
    def __init__( self ):
        
        HydrusSerialisable.SerialisableBase.__init__( self )
        
        self.engine = None
        
        self._gugs = HydrusSerialisable.SerialisableList()
        self._url_matches = HydrusSerialisable.SerialisableList()
        self._parsers = HydrusSerialisable.SerialisableList()
        self._network_contexts_to_custom_header_dicts = collections.defaultdict( dict )
        
        self._parser_namespaces = []
        
        self._gug_keys_to_display = set()
        
        self._url_match_keys_to_display = set()
        self._url_match_keys_to_parser_keys = HydrusSerialisable.SerialisableBytesDictionary()
        
        self._domains_to_url_matches = collections.defaultdict( list )
        
        import ClientImportOptions
        
        self._file_post_default_tag_import_options = ClientImportOptions.TagImportOptions()
        self._watchable_default_tag_import_options = ClientImportOptions.TagImportOptions()
        
        self._url_match_keys_to_default_tag_import_options = {}
        
        self._gug_keys_to_gugs = {}
        self._gug_names_to_gugs = {}
        
        self._parser_keys_to_parsers = {}
        
        self._dirty = False
        
        self._lock = threading.Lock()
        
        self._RecalcCache()
        
    
    def _GetDefaultTagImportOptionsForURL( self, url ):
        
        url_match = self._GetURLMatch( url )
        
        if url_match is None or url_match.GetURLType() not in ( HC.URL_TYPE_POST, HC.URL_TYPE_WATCHABLE ):
            
            return self._file_post_default_tag_import_options
            
        
        try:
            
            ( url_match, url ) = self._GetNormalisedAPIURLMatchAndURL( url )
            
        except HydrusExceptions.URLMatchException:
            
            return self._file_post_default_tag_import_options
            
        
        url_match_key = url_match.GetMatchKey()
        
        if url_match_key in self._url_match_keys_to_default_tag_import_options:
            
            return self._url_match_keys_to_default_tag_import_options[ url_match_key ]
            
        else:
            
            url_type = url_match.GetURLType()
            
            if url_type == HC.URL_TYPE_POST:
                
                return self._file_post_default_tag_import_options
                
            elif url_type == HC.URL_TYPE_WATCHABLE:
                
                return self._watchable_default_tag_import_options
                
            else:
                
                raise HydrusExceptions.URLMatchException( 'Could not find tag import options for that kind of URL Class!' )
                
            
        
    
    def _GetGUG( self, gug_key_and_name ):
        
        ( gug_key, gug_name ) = gug_key_and_name
        
        if gug_key in self._gug_keys_to_gugs:
            
            return self._gug_keys_to_gugs[ gug_key ]
            
        elif gug_name in self._gug_names_to_gugs:
            
            return self._gug_names_to_gugs[ gug_name ]
            
        else:
            
            return None
            
        
    
    def _GetNormalisedAPIURLMatchAndURL( self, url ):
        
        url_match = self._GetURLMatch( url )
        
        if url_match is None:
            
            raise HydrusExceptions.URLMatchException( 'Could not find a URL Class for ' + url + '!' )
            
        
        seen_url_matches = set()
        
        seen_url_matches.add( url_match )
        
        api_url_match = url_match
        api_url = url
        
        while api_url_match.UsesAPIURL():
            
            api_url = api_url_match.GetAPIURL( api_url )
            
            api_url_match = self._GetURLMatch( api_url )
            
            if api_url_match is None:
                
                raise HydrusExceptions.URLMatchException( 'Could not find an API URL Class for ' + api_url + ' URL, which originally came from ' + url + '!' )
                
            
            if api_url_match in seen_url_matches:
                
                loop_size = len( seen_url_matches )
                
                if loop_size == 1:
                    
                    message = 'Could not find an API URL Class for ' + url + ' as the url class API-linked to itself!'
                    
                elif loop_size == 2:
                    
                    message = 'Could not find an API URL Class for ' + url + ' as the url class and its API url class API-linked to each other!'
                    
                else:
                    
                    message = 'Could not find an API URL Class for ' + url + ' as it and its API url classes linked in a loop of size ' + HydrusData.ToHumanInt( loop_size ) + '!'
                    
                
                raise HydrusExceptions.URLMatchException( message )
                
            
            seen_url_matches.add( api_url_match )
            
        
        api_url = api_url_match.Normalise( api_url )
        
        return ( api_url_match, api_url )
        
    
    def _GetURLToFetchAndParser( self, url ):
        
        try:
            
            ( parser_url_match, parser_url ) = self._GetNormalisedAPIURLMatchAndURL( url )
            
        except HydrusExceptions.URLMatchException as e:
            
            raise HydrusExceptions.URLMatchException( 'Could not find a parser for ' + url + '!' + os.linesep * 2 + HydrusData.ToUnicode( e ) )
            
        
        url_match_key = parser_url_match.GetMatchKey()
        
        if url_match_key in self._url_match_keys_to_parser_keys:
            
            parser_key = self._url_match_keys_to_parser_keys[ url_match_key ]
            
            if parser_key is not None and parser_key in self._parser_keys_to_parsers:
                
                return ( parser_url, self._parser_keys_to_parsers[ parser_key ] )
                
            
        
        raise HydrusExceptions.URLMatchException( 'Could not find a parser for ' + parser_url_match.GetName() + ' URL Class!' )
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_gugs = self._gugs.GetSerialisableTuple()
        serialisable_gug_keys_to_display = [ gug_key.encode( 'hex' ) for gug_key in self._gug_keys_to_display ]
        
        serialisable_url_matches = self._url_matches.GetSerialisableTuple()
        serialisable_url_match_keys_to_display = [ url_match_key.encode( 'hex' ) for url_match_key in self._url_match_keys_to_display ]
        serialisable_url_match_keys_to_parser_keys = self._url_match_keys_to_parser_keys.GetSerialisableTuple()
        
        serialisable_file_post_default_tag_import_options = self._file_post_default_tag_import_options.GetSerialisableTuple()
        serialisable_watchable_default_tag_import_options = self._watchable_default_tag_import_options.GetSerialisableTuple()
        serialisable_url_match_keys_to_default_tag_import_options = [ ( url_match_key.encode( 'hex' ), tag_import_options.GetSerialisableTuple() ) for ( url_match_key, tag_import_options ) in self._url_match_keys_to_default_tag_import_options.items() ]
        
        serialisable_default_tag_import_options_tuple = ( serialisable_file_post_default_tag_import_options, serialisable_watchable_default_tag_import_options, serialisable_url_match_keys_to_default_tag_import_options )
        
        serialisable_parsers = self._parsers.GetSerialisableTuple()
        serialisable_network_contexts_to_custom_header_dicts = [ ( network_context.GetSerialisableTuple(), custom_header_dict.items() ) for ( network_context, custom_header_dict ) in self._network_contexts_to_custom_header_dicts.items() ]
        
        return ( serialisable_gugs, serialisable_gug_keys_to_display, serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsers, serialisable_network_contexts_to_custom_header_dicts )
        
    
    def _GetURLMatch( self, url ):
        
        domain = ConvertDomainIntoSecondLevelDomain( ConvertURLIntoDomain( url ) )
        
        if domain in self._domains_to_url_matches:
            
            url_matches = self._domains_to_url_matches[ domain ]
            
            for url_match in url_matches:
                
                try:
                    
                    url_match.Test( url )
                    
                    return url_match
                    
                except HydrusExceptions.URLMatchException:
                    
                    continue
                    
                
            
        
        return None
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_gugs, serialisable_gug_keys_to_display, serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsers, serialisable_network_contexts_to_custom_header_dicts ) = serialisable_info
        
        self._gugs = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_gugs )
        
        self._gug_keys_to_display = { serialisable_gug_key.decode( 'hex' ) for serialisable_gug_key in serialisable_gug_keys_to_display }
        
        self._url_matches = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_matches )
        
        self._url_match_keys_to_display = { serialisable_url_match_key.decode( 'hex' ) for serialisable_url_match_key in serialisable_url_match_keys_to_display }
        self._url_match_keys_to_parser_keys = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_match_keys_to_parser_keys )
        
        ( serialisable_file_post_default_tag_import_options, serialisable_watchable_default_tag_import_options, serialisable_url_match_keys_to_default_tag_import_options ) = serialisable_default_tag_import_options_tuple
        
        self._file_post_default_tag_import_options = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_file_post_default_tag_import_options )
        self._watchable_default_tag_import_options = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_watchable_default_tag_import_options )
        
        self._url_match_keys_to_default_tag_import_options = { serialisable_url_match_key.decode( 'hex' ) : HydrusSerialisable.CreateFromSerialisableTuple( serialisable_tag_import_options ) for ( serialisable_url_match_key, serialisable_tag_import_options ) in serialisable_url_match_keys_to_default_tag_import_options }
        
        self._parsers = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_parsers )
        
        self._network_contexts_to_custom_header_dicts = collections.defaultdict( dict )
        
        for ( serialisable_network_context, custom_header_dict_items ) in serialisable_network_contexts_to_custom_header_dicts:
            
            network_context = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_network_context )
            custom_header_dict = dict( custom_header_dict_items )
            
            self._network_contexts_to_custom_header_dicts[ network_context ] = custom_header_dict
            
        
    
    def _RecalcCache( self ):
        
        self._domains_to_url_matches = collections.defaultdict( list )
        
        for url_match in self._url_matches:
            
            domain = url_match.GetDomain()
            
            self._domains_to_url_matches[ domain ].append( url_match )
            
        
        for url_matches in self._domains_to_url_matches.values():
            
            NetworkDomainManager.STATICSortURLMatchesDescendingComplexity( url_matches )
            
        
        self._gug_keys_to_gugs = { gug.GetGUGKey() : gug for gug in self._gugs }
        self._gug_names_to_gugs = { gug.GetName() : gug for gug in self._gugs }
        
        self._parser_keys_to_parsers = { parser.GetParserKey() : parser for parser in self._parsers }
        
        namespaces = set()
        
        for parser in self._parsers:
            
            namespaces.update( parser.GetNamespaces() )
            
        
        self._parser_namespaces = list( namespaces )
        
        self._parser_namespaces.sort()
        
    
    def _SetDirty( self ):
        
        self._dirty = True
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( serialisable_url_matches, serialisable_network_contexts_to_custom_header_dicts ) = old_serialisable_info
            
            url_matches = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_matches )
            
            url_match_names_to_display = {}
            url_match_names_to_page_parser_keys = HydrusSerialisable.SerialisableBytesDictionary()
            url_match_names_to_gallery_parser_keys = HydrusSerialisable.SerialisableBytesDictionary()
            
            for url_match in url_matches:
                
                name = url_match.GetName()
                
                if url_match.IsPostURL():
                    
                    url_match_names_to_display[ name ] = True
                    
                    url_match_names_to_page_parser_keys[ name ] = None
                    
                
                if url_match.IsGalleryURL() or url_match.IsWatchableURL():
                    
                    url_match_names_to_gallery_parser_keys[ name ] = None
                    
                
            
            serialisable_url_match_names_to_display = url_match_names_to_display.items()
            serialisable_url_match_names_to_page_parser_keys = url_match_names_to_page_parser_keys.GetSerialisableTuple()
            serialisable_url_match_names_to_gallery_parser_keys = url_match_names_to_gallery_parser_keys.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_url_matches, serialisable_url_match_names_to_display, serialisable_url_match_names_to_page_parser_keys, serialisable_url_match_names_to_gallery_parser_keys, serialisable_network_contexts_to_custom_header_dicts )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( serialisable_url_matches, serialisable_url_match_names_to_display, serialisable_url_match_names_to_page_parser_keys, serialisable_url_match_names_to_gallery_parser_keys, serialisable_network_contexts_to_custom_header_dicts ) = old_serialisable_info
            
            parsers = HydrusSerialisable.SerialisableList()
            
            serialisable_parsing_parsers = parsers.GetSerialisableTuple()
            
            url_match_names_to_display = dict( serialisable_url_match_names_to_display )
            
            url_match_keys_to_display = []
            
            url_match_names_to_gallery_parser_keys = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_match_names_to_gallery_parser_keys )
            url_match_names_to_page_parser_keys = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_match_names_to_page_parser_keys )
            
            url_match_keys_to_parser_keys = HydrusSerialisable.SerialisableBytesDictionary()
            
            url_matches = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_url_matches )
            
            for url_match in url_matches:
                
                url_match_key = url_match.GetMatchKey()
                
                name = url_match.GetName()
                
                if name in url_match_names_to_display and url_match_names_to_display[ name ]:
                    
                    url_match_keys_to_display.append( url_match_key )
                    
                
            
            serialisable_url_matches = url_matches.GetSerialisableTuple() # added random key this week, so save these changes back again!
            
            serialisable_url_match_keys_to_display = [ url_match_key.encode( 'hex' ) for url_match_key in url_match_keys_to_display ]
            
            serialisable_url_match_keys_to_parser_keys = url_match_keys_to_parser_keys.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts )
            
            return ( 3, new_serialisable_info )
            
        
        if version == 3:
            
            ( serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts ) = old_serialisable_info
            
            import ClientImportOptions
            
            self._file_post_default_tag_import_options = ClientImportOptions.TagImportOptions()
            self._watchable_default_tag_import_options = ClientImportOptions.TagImportOptions()
            
            self._url_match_keys_to_default_tag_import_options = {}
            
            serialisable_file_post_default_tag_import_options = self._file_post_default_tag_import_options.GetSerialisableTuple()
            serialisable_watchable_default_tag_import_options = self._watchable_default_tag_import_options.GetSerialisableTuple()
            serialisable_url_match_keys_to_default_tag_import_options = [ ( url_match_key.encode( 'hex' ), tag_import_options.GetSerialisableTuple() ) for ( url_match_key, tag_import_options ) in self._url_match_keys_to_default_tag_import_options.items() ]
            
            serialisable_default_tag_import_options_tuple = ( serialisable_file_post_default_tag_import_options, serialisable_watchable_default_tag_import_options, serialisable_url_match_keys_to_default_tag_import_options )
            
            new_serialisable_info = ( serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts )
            
            return ( 4, new_serialisable_info )
            
        
        if version == 4:
            
            ( serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts ) = old_serialisable_info
            
            gugs = HydrusSerialisable.SerialisableList()
            
            serialisable_gugs = gugs.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_gugs, serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts )
            
            return ( 5, new_serialisable_info )
            
        
        if version == 5:
            
            ( serialisable_gugs, serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts ) = old_serialisable_info
            
            gugs = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_gugs )
            
            gug_keys_to_display = [ gug.GetGUGKey() for gug in gugs if 'ugoira' not in gug.GetName() ]
            
            serialisable_gug_keys_to_display = [ gug_key.encode( 'hex' ) for gug_key in gug_keys_to_display ]
            
            new_serialisable_info = ( serialisable_gugs, serialisable_gug_keys_to_display, serialisable_url_matches, serialisable_url_match_keys_to_display, serialisable_url_match_keys_to_parser_keys, serialisable_default_tag_import_options_tuple, serialisable_parsing_parsers, serialisable_network_contexts_to_custom_header_dicts )
            
            return ( 6, new_serialisable_info )
            
        
    
    def AddGUGs( self, new_gugs ):
        
        with self._lock:
            
            gugs = list( self._gugs )
            
            for gug in new_gugs:
                
                gug.SetNonDupeName( [ g.GetName() for g in gugs ] )
                
                gugs.append( gug )
                
            
        
        self.SetGUGs( gugs )
        
    
    def AddParsers( self, new_parsers ):
        
        with self._lock:
            
            parsers = list( self._parsers )
            
            for parser in new_parsers:
                
                parser.SetNonDupeName( [ p.GetName() for p in parsers ] )
                
                parsers.append( parser )
                
            
        
        self.SetParsers( parsers )
        
    
    def AddURLMatches( self, new_url_matches ):
        
        with self._lock:
            
            url_matches = list( self._url_matches )
            
            for url_match in new_url_matches:
                
                url_match.SetNonDupeName( [ u.GetName() for u in url_matches ] )
                
                url_matches.append( url_match )
                
            
        
        self.SetURLMatches( url_matches )
        
    
    def AlreadyHaveExactlyTheseHeaders( self, network_context, headers_list ):
        
        with self._lock:
            
            if network_context in self._network_contexts_to_custom_header_dicts:
                
                custom_headers_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                
                if len( headers_list ) != len( custom_headers_dict ):
                    
                    return False
                    
                
                for ( key, value, reason ) in headers_list:
                    
                    if key not in custom_headers_dict:
                        
                        return False
                        
                    
                    ( existing_value, existing_approved, existing_reason ) = custom_headers_dict[ key ]
                    
                    if existing_value != value:
                        
                        return False
                        
                    
                
                return True
                
            
        
        return False
        
    
    def AlreadyHaveExactlyThisGUG( self, new_gug ):
        
        with self._lock:
            
            # absent irrelevant variables, do we have the exact same object already in?
            
            gug_key_and_name = new_gug.GetGUGKeyAndName()
            
            dupe_gugs = [ gug.Duplicate() for gug in self._gugs ]
            
            for dupe_gug in dupe_gugs:
                
                dupe_gug.SetGUGKeyAndName( gug_key_and_name )
                
                if dupe_gug.DumpToString() == new_gug.DumpToString():
                    
                    return True
                    
                
            
        
        return False
        
    
    def AlreadyHaveExactlyThisParser( self, new_parser ):
        
        with self._lock:
            
            # absent irrelevant variables, do we have the exact same object already in?
            
            new_name = new_parser.GetName()
            new_parser_key = new_parser.GetParserKey()
            new_example_urls = new_parser.GetExampleURLs()
            new_example_parsing_context = new_parser.GetExampleParsingContext()
            
            dupe_parsers = [ ( parser.Duplicate(), parser ) for parser in self._parsers ]
            
            for ( dupe_parser, parser ) in dupe_parsers:
                
                dupe_parser.SetName( new_name )
                dupe_parser.SetParserKey( new_parser_key )
                dupe_parser.SetExampleURLs( new_example_urls )
                dupe_parser.SetExampleParsingContext( new_example_parsing_context )
                
                if dupe_parser.DumpToString() == new_parser.DumpToString():
                    
                    # since these are the 'same', let's merge example urls
                    
                    parser_example_urls = set( parser.GetExampleURLs() )
                    
                    parser_example_urls.update( new_example_urls )
                    
                    parser_example_urls = list( parser_example_urls )
                    
                    parser.SetExampleURLs( parser_example_urls )
                    
                    self._SetDirty()
                    
                    return True
                    
                
            
        
        return False
        
    
    def AlreadyHaveExactlyThisURLMatch( self, new_url_match ):
        
        with self._lock:
            
            # absent irrelevant variables, do we have the exact same object already in?
            
            name = new_url_match.GetName()
            match_key = new_url_match.GetMatchKey()
            example_url = new_url_match.GetExampleURL()
            
            dupe_url_matches = [ url_match.Duplicate() for url_match in self._url_matches ]
            
            for dupe_url_match in dupe_url_matches:
                
                dupe_url_match.SetName( name )
                dupe_url_match.SetMatchKey( match_key )
                dupe_url_match.SetExampleURL( example_url )
                
                if dupe_url_match.DumpToString() == new_url_match.DumpToString():
                    
                    return True
                    
                
            
        
        return False
        
    
    def AutoAddDomainMetadatas( self, domain_metadatas, approved = False ):
        
        for domain_metadata in domain_metadatas:
            
            if not domain_metadata.HasHeaders():
                
                continue
                
            
            with self._lock:
                
                domain = domain_metadata.GetDomain()
                
                network_context = ClientNetworkingContexts.NetworkContext( CC.NETWORK_CONTEXT_DOMAIN, domain )
                
                headers_list = domain_metadata.GetHeaders()
                
                custom_headers_dict = { key : ( value, approved, reason ) for ( key, value, reason ) in headers_list }
                
                self._network_contexts_to_custom_header_dicts[ network_context ] = custom_headers_dict
                
            
        
    
    def AutoAddURLMatchesAndParsers( self, new_url_matches, dupe_url_matches, new_parsers ):
        
        for url_match in new_url_matches:
            
            url_match.RegenerateMatchKey()
            
        
        for parser in new_parsers:
            
            parser.RegenerateParserKey()
            
        
        # any existing url matches that already do the job of the new ones should be hung on to but renamed
        
        with self._lock:
            
            prefix = 'zzz - renamed due to auto-import - '
            
            renamees = []
            
            for existing_url_match in self._url_matches:
                
                if existing_url_match.GetName().startswith( prefix ):
                    
                    continue
                    
                
                for new_url_match in new_url_matches:
                    
                    if new_url_match.Matches( existing_url_match.GetExampleURL() ) and existing_url_match.Matches( new_url_match.GetExampleURL() ):
                        
                        # the url matches match each other, so they are doing the same job
                        
                        renamees.append( existing_url_match )
                        
                        break
                        
                    
                
                
            
            for renamee in renamees:
                
                existing_names = [ url_match.GetName() for url_match in self._url_matches if url_match != renamee ]
                
                renamee.SetName( prefix + renamee.GetName() )
                
                renamee.SetNonDupeName( existing_names )
                
            
        
        self.AddURLMatches( new_url_matches )
        self.AddParsers( new_parsers )
        
        # we want to match these url matches and parsers together if possible
        
        with self._lock:
            
            url_matches_to_link = list( new_url_matches )
            
            # if downloader adds existing url match but updated parser, we want to update the existing link
            
            for dupe_url_match in dupe_url_matches:
                
                # this is to make sure we have the right match keys for the link update in a minute
                
                actual_existing_dupe_url_match = self._GetURLMatch( dupe_url_match.GetExampleURL() )
                
                if actual_existing_dupe_url_match is not None:
                    
                    url_matches_to_link.append( actual_existing_dupe_url_match )
                    
                
            
            new_url_match_keys_to_parser_keys = NetworkDomainManager.STATICLinkURLMatchesAndParsers( url_matches_to_link, new_parsers, {} )
            
            self._url_match_keys_to_parser_keys.update( new_url_match_keys_to_parser_keys )
            
        
        # let's do a trytolink just in case there are loose ends due to some dupe being discarded earlier (e.g. url match is new, but parser was not).
        
        self.TryToLinkURLMatchesAndParsers()
        
    
    def CanValidateInPopup( self, network_contexts ):
        
        # we can always do this for headers
        
        return True
        
    
    def ConvertURLsToMediaViewerTuples( self, urls ):
        
        url_tuples = []
        
        with self._lock:
            
            for url in urls:
                
                url_match = self._GetURLMatch( url )
                
                if url_match is None:
                    
                    if False:
                        
                        domain = ConvertURLIntoDomain( url )
                        
                        url_tuples.append( ( domain, url ) )
                        
                    
                else:
                    
                    url_match_key = url_match.GetMatchKey()
                    
                    if url_match_key in self._url_match_keys_to_display:
                        
                        url_match_name = url_match.GetName()
                        
                        url_tuples.append( ( url_match_name, url ) )
                        
                    
                
                if len( url_tuples ) == 10:
                    
                    break
                    
                
            
        
        url_tuples.sort()
        
        return url_tuples
        
    
    def DeleteGUGs( self, deletee_names ):
        
        with self._lock:
            
            gugs = [ gug for gug in self._gugs if gug.GetName() not in deletee_names ]
            
        
        self.SetGUGs( gugs )
        
    
    def GenerateValidationPopupProcess( self, network_contexts ):
        
        with self._lock:
            
            header_tuples = []
            
            for network_context in network_contexts:
                
                if network_context in self._network_contexts_to_custom_header_dicts:
                    
                    custom_header_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                    
                    for ( key, ( value, approved, reason ) ) in custom_header_dict.items():
                        
                        if approved == VALID_UNKNOWN:
                            
                            header_tuples.append( ( network_context, key, value, reason ) )
                            
                        
                    
                
            
            process = DomainValidationPopupProcess( self, header_tuples )
            
            return process
            
        
    
    def GetDefaultGUGKeyAndName( self ):
        
        with self._lock:
            
            gug_key = HG.client_controller.new_options.GetKey( 'default_gug_key' )
            gug_name = HG.client_controller.new_options.GetString( 'default_gug_name' )
            
            return ( gug_key, gug_name )
            
        
    
    def GetDefaultTagImportOptions( self ):
        
        with self._lock:
            
            return ( self._file_post_default_tag_import_options, self._watchable_default_tag_import_options, self._url_match_keys_to_default_tag_import_options )
            
        
    
    def GetDefaultTagImportOptionsForPosts( self ):
        
        with self._lock:
            
            return self._file_post_default_tag_import_options.Duplicate()
            
        
    
    def GetDefaultTagImportOptionsForURL( self, url ):
        
        with self._lock:
            
            return self._GetDefaultTagImportOptionsForURL( url )
            
        
    
    def GetDownloader( self, url ):
        
        with self._lock:
            
            # this might be better as getdownloaderkey, but we'll see how it shakes out
            # might also be worth being a getifhasdownloader
            
            # match the url to a url_match, then lookup that in a 'this downloader can handle this url_match type' dict that we'll manage
            
            pass
            
        
    
    def GetGUG( self, gug_key_and_name ):
        
        with self._lock:
            
            return self._GetGUG( gug_key_and_name )
            
        
    
    def GetGUGs( self ):
        
        with self._lock:
            
            return list( self._gugs )
            
        
    
    def GetGUGKeysToDisplay( self ):
        
        with self._lock:
            
            return set( self._gug_keys_to_display )
            
        
    
    def GetHeaders( self, network_contexts ):
        
        with self._lock:
            
            headers = {}
            
            for network_context in network_contexts:
                
                if network_context in self._network_contexts_to_custom_header_dicts:
                    
                    custom_header_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                    
                    for ( key, ( value, approved, reason ) ) in custom_header_dict.items():
                        
                        if approved == VALID_APPROVED:
                            
                            headers[ key ] = value
                            
                        
                    
                
            
            return headers
            
        
    
    def GetInitialSearchText( self, gug_key_and_name ):
        
        with self._lock:
            
            gug = self._GetGUG( gug_key_and_name )
            
            if gug is None:
                
                return 'unknown downloader'
                
            else:
                
                return gug.GetInitialSearchText()
                
            
        
    
    def GetNetworkContextsToCustomHeaderDicts( self ):
        
        with self._lock:
            
            return dict( self._network_contexts_to_custom_header_dicts )
            
        
    
    def GetParser( self, name ):
        
        with self._lock:
            
            for parser in self._parsers:
                
                if parser.GetName() == name:
                    
                    return parser
                    
                
            
        
        return None
        
    
    def GetParsers( self ):
        
        with self._lock:
            
            return list( self._parsers )
            
        
    
    def GetParserNamespaces( self ):
        
        with self._lock:
            
            return list( self._parser_namespaces )
            
        
    
    def GetShareableCustomHeaders( self, network_context ):
        
        with self._lock:
            
            headers_list = []
            
            if network_context in self._network_contexts_to_custom_header_dicts:
                
                custom_header_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                
                for ( key, ( value, approved, reason ) ) in custom_header_dict.items():
                    
                    headers_list.append( ( key, value, reason ) )
                    
                
            
            return headers_list
            
        
    
    def GetURLMatch( self, url ):
        
        with self._lock:
            
            return self._GetURLMatch( url )
            
        
    
    def GetURLMatches( self ):
        
        with self._lock:
            
            return list( self._url_matches )
            
        
    
    def GetURLMatchKeysToParserKeys( self ):
        
        with self._lock:
            
            return dict( self._url_match_keys_to_parser_keys )
            
        
    
    def GetURLMatchKeysToDisplay( self ):
        
        with self._lock:
            
            return set( self._url_match_keys_to_display )
            
        
    
    def GetURLParseCapability( self, url ):
        
        with self._lock:
            
            url_match = self._GetURLMatch( url )
            
            if url_match is None:
                
                return ( HC.URL_TYPE_UNKNOWN, 'unknown url', False )
                
            
            url_type = url_match.GetURLType()
            match_name = url_match.GetName()
            
            try:
                
                ( url_to_fetch, parser ) = self._GetURLToFetchAndParser( url )
                
                can_parse = True
                
            except HydrusExceptions.URLMatchException:
                
                can_parse = False
                
            
        
        return ( url_type, match_name, can_parse )
        
    
    def GetURLToFetchAndParser( self, url ):
        
        with self._lock:
            
            result = self._GetURLToFetchAndParser( url )
            
            if HG.network_report_mode:
                
                ( url_to_fetch, parser ) = result
                
                HydrusData.ShowText( 'URL to fetch and parser request: ' + url + ' -> ' + url_to_fetch + ': ' + parser.GetName() )
                
            
            return result
            
        
    
    def HasCustomHeaders( self, network_context ):
        
        with self._lock:
            
            return network_context in self._network_contexts_to_custom_header_dicts and len( self._network_contexts_to_custom_header_dicts[ network_context ] ) > 0
            
        
    
    def Initialise( self ):
        
        self._RecalcCache()
        
    
    def IsDirty( self ):
        
        with self._lock:
            
            return self._dirty
            
        
    
    def IsValid( self, network_contexts ):
        
        # for now, let's say that denied headers are simply not added, not that they invalidate a query
        
        for network_context in network_contexts:
            
            if network_context in self._network_contexts_to_custom_header_dicts:
                
                custom_header_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                
                for ( value, approved, reason ) in custom_header_dict.values():
                    
                    if approved == VALID_UNKNOWN:
                        
                        return False
                        
                    
                
            
        
        return True
        
    
    def NormaliseURL( self, url ):
        
        with self._lock:
            
            url_match = self._GetURLMatch( url )
            
            if url_match is None:
                
                p = urlparse.urlparse( url )
                
                scheme = p.scheme
                netloc = p.netloc
                path = p.path
                params = p.params
                query = AlphabetiseQueryText( p.query )
                fragment = p.fragment
                
                r = urlparse.ParseResult( scheme, netloc, path, params, query, fragment )
                
                normalised_url = r.geturl()
                
            else:
                
                normalised_url = url_match.Normalise( url )
                
            
            return normalised_url
            
        
    
    def OverwriteDefaultGUGs( self, gug_names ):
        
        with self._lock:
            
            import ClientDefaults
            
            default_gugs = ClientDefaults.GetDefaultGUGs()
            
            for gug in default_gugs:
                
                gug.RegenerateGUGKey()
                
            
            existing_gugs = list( self._gugs )
            
            new_gugs = [ gug for gug in existing_gugs if gug.GetName() not in gug_names ]
            new_gugs.extend( [ gug for gug in default_gugs if gug.GetName() in gug_names ] )
            
        
        self.SetGUGs( new_gugs )
        
    
    def OverwriteDefaultParsers( self, parser_names ):
        
        with self._lock:
            
            import ClientDefaults
            
            default_parsers = ClientDefaults.GetDefaultParsers()
            
            for parser in default_parsers:
                
                parser.RegenerateParserKey()
                
            
            existing_parsers = list( self._parsers )
            
            new_parsers = [ parser for parser in existing_parsers if parser.GetName() not in parser_names ]
            new_parsers.extend( [ parser for parser in default_parsers if parser.GetName() in parser_names ] )
            
        
        self.SetParsers( new_parsers )
        
    
    def OverwriteDefaultURLMatches( self, url_match_names ):
        
        with self._lock:
            
            import ClientDefaults
            
            default_url_matches = ClientDefaults.GetDefaultURLMatches()
            
            for url_match in default_url_matches:
                
                url_match.RegenerateMatchKey()
                
            
            existing_url_matches = list( self._url_matches )
            
            new_url_matches = [ url_match for url_match in existing_url_matches if url_match.GetName() not in url_match_names ]
            new_url_matches.extend( [ url_match for url_match in default_url_matches if url_match.GetName() in url_match_names ] )
            
        
        self.SetURLMatches( new_url_matches )
        
    
    def OverwriteParserLink( self, url_match, parser ):
        
        with self._lock:
            
            url_match_key = url_match.GetMatchKey()
            parser_key = parser.GetParserKey()
            
            self._url_match_keys_to_parser_keys[ url_match_key ] = parser_key
            
        
    
    def SetClean( self ):
        
        with self._lock:
            
            self._dirty = False
            
        
    
    def SetDefaultGUGKeyAndName( self, gug_key_and_name ):
        
        with self._lock:
            
            ( gug_key, gug_name ) = gug_key_and_name
            
            HG.client_controller.new_options.SetKey( 'default_gug_key', gug_key )
            HG.client_controller.new_options.SetString( 'default_gug_name', gug_name )
            
        
    
    def SetDefaultTagImportOptions( self, file_post_default_tag_import_options, watchable_default_tag_import_options, url_match_keys_to_tag_import_options ):
        
        with self._lock:
            
            self._file_post_default_tag_import_options = file_post_default_tag_import_options
            self._watchable_default_tag_import_options = watchable_default_tag_import_options
            
            self._url_match_keys_to_default_tag_import_options = url_match_keys_to_tag_import_options
            
            self._SetDirty()
            
        
    
    def SetGUGs( self, gugs ):
        
        with self._lock:
            
            # by default, we will show new gugs
            
            old_gug_keys = { gug.GetGUGKey() for gug in self._gugs }
            gug_keys = { gug.GetGUGKey() for gug in gugs }
            
            added_gug_keys = gug_keys.difference( old_gug_keys )
            
            self._gug_keys_to_display.update( added_gug_keys )
            
            #
            
            self._gugs = HydrusSerialisable.SerialisableList( gugs )
            
            self._RecalcCache()
            
            self._SetDirty()
            
        
    
    def SetGUGKeysToDisplay( self, gug_keys_to_display ):
        
        with self._lock:
            
            self._gug_keys_to_display = set()
            
            self._gug_keys_to_display.update( gug_keys_to_display )
            
            self._SetDirty()
            
        
    
    def SetHeaderValidation( self, network_context, key, approved ):
        
        with self._lock:
            
            if network_context in self._network_contexts_to_custom_header_dicts:
                
                custom_header_dict = self._network_contexts_to_custom_header_dicts[ network_context ]
                
                if key in custom_header_dict:
                    
                    ( value, old_approved, reason ) = custom_header_dict[ key ]
                    
                    custom_header_dict[ key ] = ( value, approved, reason )
                    
                
            
            self._SetDirty()
            
        
    
    def SetNetworkContextsToCustomHeaderDicts( self, network_contexts_to_custom_header_dicts ):
        
        with self._lock:
            
            self._network_contexts_to_custom_header_dicts = network_contexts_to_custom_header_dicts
            
            self._SetDirty()
            
        
    
    def SetParsers( self, parsers ):
        
        with self._lock:
            
            self._parsers = HydrusSerialisable.SerialisableList()
            
            self._parsers.extend( parsers )
            
            self._parsers.sort( key = lambda p: p.GetName() )
            
            # delete orphans
            
            parser_keys = { parser.GetParserKey() for parser in parsers }
            
            deletee_url_match_keys = set()
            
            for ( url_match_key, parser_key ) in self._url_match_keys_to_parser_keys.items():
                
                if parser_key not in parser_keys:
                    
                    deletee_url_match_keys.add( url_match_key )
                    
                
            
            for deletee_url_match_key in deletee_url_match_keys:
                
                del self._url_match_keys_to_parser_keys[ deletee_url_match_key ]
                
            
            #
            
            self._RecalcCache()
            
            self._SetDirty()
            
        
    
    def SetURLMatches( self, url_matches ):
        
        with self._lock:
            
            # by default, we will show post urls
            
            old_post_url_match_keys = { url_match.GetMatchKey() for url_match in self._url_matches if url_match.IsPostURL() }
            post_url_match_keys = { url_match.GetMatchKey() for url_match in url_matches if url_match.IsPostURL() }
            
            added_post_url_match_keys = post_url_match_keys.difference( old_post_url_match_keys )
            
            self._url_match_keys_to_display.update( added_post_url_match_keys )
            
            #
            
            self._url_matches = HydrusSerialisable.SerialisableList()
            
            self._url_matches.extend( url_matches )
            
            self._url_matches.sort( key = lambda u: u.GetName() )
            
            #
            
            # delete orphans
            
            url_match_keys = { url_match.GetMatchKey() for url_match in url_matches }
            
            self._url_match_keys_to_display.intersection_update( url_match_keys )
            
            for deletee_key in set( self._url_match_keys_to_parser_keys.keys() ).difference( url_match_keys ):
                
                del self._url_match_keys_to_parser_keys[ deletee_key ]
                
            
            # any url matches that link to another via the API conversion will not be using parsers
            
            url_match_api_pairs = ConvertURLMatchesIntoAPIPairs( self._url_matches )
            
            for ( url_match_original, url_match_api ) in url_match_api_pairs:
                
                url_match_key = url_match_original.GetMatchKey()
                
                if url_match_key in self._url_match_keys_to_parser_keys:
                    
                    del self._url_match_keys_to_parser_keys[ url_match_key ]
                    
                
            
            self._RecalcCache()
            
            self._SetDirty()
            
        
    
    def SetURLMatchKeysToParserKeys( self, url_match_keys_to_parser_keys ):
        
        with self._lock:
            
            self._url_match_keys_to_parser_keys = HydrusSerialisable.SerialisableBytesDictionary()
            
            self._url_match_keys_to_parser_keys.update( url_match_keys_to_parser_keys )
            
            self._SetDirty()
            
        
    
    def SetURLMatchKeysToDisplay( self, url_match_keys_to_display ):
        
        with self._lock:
            
            self._url_match_keys_to_display = set()
            
            self._url_match_keys_to_display.update( url_match_keys_to_display )
            
            self._SetDirty()
            
        
    
    def ShouldAssociateURLWithFiles( self, url ):
        
        with self._lock:
            
            url_match = self._GetURLMatch( url )
            
            if url_match is None:
                
                return True
                
            
            return url_match.ShouldAssociateWithFiles()
            
        
    
    def TryToLinkURLMatchesAndParsers( self ):
        
        with self._lock:
            
            new_url_match_keys_to_parser_keys = NetworkDomainManager.STATICLinkURLMatchesAndParsers( self._url_matches, self._parsers, self._url_match_keys_to_parser_keys )
            
            self._url_match_keys_to_parser_keys.update( new_url_match_keys_to_parser_keys )
            
            self._SetDirty()
            
        
    
    def URLCanReferToMultipleFiles( self, url ):
        
        with self._lock:
            
            url_match = self._GetURLMatch( url )
            
            if url_match is None:
                
                return False
                
            
            return url_match.CanReferToMultipleFiles()
            
        
    
    def URLDefinitelyRefersToOneFile( self, url ):
        
        with self._lock:
            
            url_match = self._GetURLMatch( url )
            
            if url_match is None:
                
                return False
                
            
            return url_match.RefersToOneFile()
            
        
    
    @staticmethod
    def STATICLinkURLMatchesAndParsers( url_matches, parsers, existing_url_match_keys_to_parser_keys ):
        
        url_matches = list( url_matches )
        
        NetworkDomainManager.STATICSortURLMatchesDescendingComplexity( url_matches )
        
        parsers = list( parsers )
        
        parsers.sort( key = lambda p: p.GetName() )
        
        new_url_match_keys_to_parser_keys = {}
        
        api_pairs = ConvertURLMatchesIntoAPIPairs( url_matches )
        
        # anything that goes to an api url will be parsed by that api's parser--it can't have its own
        api_pair_unparsable_url_matches = set()
        
        for ( a, b ) in api_pairs:
            
            api_pair_unparsable_url_matches.add( a )
            
        
        #
        
        # I have to do this backwards, going through parsers and then url_matches, so I can do a proper url match lookup like the real domain manager does it
        # otherwise, if we iterate through url matches looking for parsers to match them, we have gallery url matches thinking they match parser post urls
        # e.g.
        # The page parser might say it supports https://danbooru.donmai.us/posts/3198277
        # But the gallery url class might think it recognises that as https://danbooru.donmai.us/posts
        # 
        # So we have to do the normal lookup in the proper descending complexity order, not searching any further than the first, correct match
        
        for parser in parsers:
            
            example_urls = parser.GetExampleURLs()
            
            for example_url in example_urls:
                
                for url_match in url_matches:
                    
                    if url_match.Matches( example_url ):
                        
                        # we have a match. this is the 'correct' match for this example url, and we should not search any more, so we break below
                        
                        url_match_key = url_match.GetMatchKey()
                        
                        parsable = url_match.IsParsable()
                        linkable = url_match_key not in existing_url_match_keys_to_parser_keys and url_match_key not in new_url_match_keys_to_parser_keys
                        
                        if parsable and linkable:
                            
                            new_url_match_keys_to_parser_keys[ url_match_key ] = parser.GetParserKey()
                            
                        
                        break
                        
                    
                
            
        '''
        #
        
        for url_match in url_matches:
            
            if not url_match.IsParsable() or url_match in api_pair_unparsable_url_matches:
                
                continue
                
            
            url_match_key = url_match.GetMatchKey()
            
            if url_match_key in existing_url_match_keys_to_parser_keys:
                
                continue
                
            
            for parser in parsers:
                
                example_urls = parser.GetExampleURLs()
                
                if True in ( url_match.Matches( example_url ) for example_url in example_urls ):
                    
                    new_url_match_keys_to_parser_keys[ url_match_key ] = parser.GetParserKey()
                    
                    break
                    
                
            
        '''
        return new_url_match_keys_to_parser_keys
        
    
    @staticmethod
    def STATICSortURLMatchesDescendingComplexity( url_matches ):
        
        # we sort them in descending complexity so that
        # post url/manga subpage
        # is before
        # post url
        
        # also, put more 'precise' URL types above more typically permissive, in the order:
        # file
        # post
        # gallery/watchable
        # sorting in reverse, so higher number means more precise
        
        def key( u_m ):
            
            u_t = u_m.GetURLType()
            
            if u_t == HC.URL_TYPE_FILE:
                
                u_t_precision_value = 2
                
            elif u_t == HC.URL_TYPE_POST:
                
                u_t_precision_value = 1
                
            else:
                
                u_t_precision_value = 0
                
            
            u_e = u_m.GetExampleURL()
            
            return ( u_t_precision_value, u_e.count( '/' ), u_e.count( '=' ) )
            
        
        url_matches.sort( key = key, reverse = True )
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_NETWORK_DOMAIN_MANAGER ] = NetworkDomainManager

class DomainMetadataPackage( HydrusSerialisable.SerialisableBase ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_DOMAIN_METADATA_PACKAGE
    SERIALISABLE_NAME = 'Domain Metadata'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, domain = None, headers_list = None, bandwidth_rules = None ):
        
        HydrusSerialisable.SerialisableBase.__init__( self )
        
        if domain is None:
            
            domain = 'example.com'
            
        
        self._domain = domain
        self._headers_list = headers_list
        self._bandwidth_rules = bandwidth_rules
        
    
    def _GetSerialisableInfo( self ):
        
        if self._bandwidth_rules is None:
            
            serialisable_bandwidth_rules = self._bandwidth_rules
            
        else:
            
            serialisable_bandwidth_rules = self._bandwidth_rules.GetSerialisableTuple()
            
        
        return ( self._domain, self._headers_list, serialisable_bandwidth_rules )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( self._domain, self._headers_list, serialisable_bandwidth_rules ) = serialisable_info
        
        if serialisable_bandwidth_rules is None:
            
            self._bandwidth_rules = serialisable_bandwidth_rules
            
        else:
            
            self._bandwidth_rules = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_bandwidth_rules )
            
        
    
    def GetBandwidthRules( self ):
        
        return self._bandwidth_rules
        
    
    def GetDetailedSafeSummary( self ):
        
        components = [ 'For domain "' + self._domain + '":' ]
        
        if self.HasBandwidthRules():
            
            m = 'Bandwidth rules: '
            m += os.linesep
            m += os.linesep.join( [ HydrusNetworking.ConvertBandwidthRuleToString( rule ) for rule in self._bandwidth_rules.GetRules() ] )
            
            components.append( m )
            
        
        if self.HasHeaders():
            
            m = 'Headers: '
            m += os.linesep
            m += os.linesep.join( [ key + ' : ' + value + ' - ' + reason for ( key, value, reason ) in self._headers_list ] )
            
            components.append( m )
            
        
        joiner = os.linesep * 2
        
        s = joiner.join( components )
        
        return s
        
    
    def GetDomain( self ):
        
        return self._domain
        
    
    def GetHeaders( self ):
        
        return self._headers_list
        
    
    def GetSafeSummary( self ):
        
        components = []
        
        if self.HasBandwidthRules():
            
            components.append( 'bandwidth rules' )
            
        
        if self.HasHeaders():
            
            components.append( 'headers' )
            
        
        return ' and '.join( components ) + ' - ' + self._domain
        
    
    def HasBandwidthRules( self ):
        
        return self._bandwidth_rules is not None
        
    
    def HasHeaders( self ):
        
        return self._headers_list is not None
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_DOMAIN_METADATA_PACKAGE ] = DomainMetadataPackage

class DomainValidationPopupProcess( object ):
    
    def __init__( self, domain_manager, header_tuples ):
        
        self._domain_manager = domain_manager
        
        self._header_tuples = header_tuples
        
        self._is_done = False
        
    
    def IsDone( self ):
        
        return self._is_done
        
    
    def Start( self ):
        
        try:
            
            results = []
            
            for ( network_context, key, value, reason ) in self._header_tuples:
                
                job_key = ClientThreading.JobKey()
                
                # generate question
                
                question = 'For the network context ' + network_context.ToUnicode() + ', can the client set this header?'
                question += os.linesep * 2
                question += key + ': ' + value
                question += os.linesep * 2
                question += reason
                
                job_key.SetVariable( 'popup_yes_no_question', question )
                
                HG.client_controller.pub( 'message', job_key )
                
                result = job_key.GetIfHasVariable( 'popup_yes_no_answer' )
                
                while result is None:
                    
                    if HG.view_shutdown:
                        
                        return
                        
                    
                    time.sleep( 0.25 )
                    
                    result = job_key.GetIfHasVariable( 'popup_yes_no_answer' )
                    
                
                if result:
                    
                    approved = VALID_APPROVED
                    
                else:
                    
                    approved = VALID_DENIED
                    
                
                self._domain_manager.SetHeaderValidation( network_context, key, approved )
                
            
        finally:
            
            self._is_done = True
            
        
    
GALLERY_INDEX_TYPE_PATH_COMPONENT = 0
GALLERY_INDEX_TYPE_PARAMETER = 1

class GalleryURLGenerator( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_GALLERY_URL_GENERATOR
    SERIALISABLE_NAME = 'Gallery URL Generator'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, name, gug_key = None, url_template = None, replacement_phrase = None, search_terms_separator = None, initial_search_text = None, example_search_text = None ):
        
        if gug_key is None:
            
            gug_key = HydrusData.GenerateKey()
            
        
        if url_template is None:
            
            url_template = 'https://example.com/search?q=%tags%&index=0'
            
        
        if replacement_phrase is None:
            
            replacement_phrase = '%tags%'
            
        
        if search_terms_separator is None:
            
            search_terms_separator = '+'
            
        
        if initial_search_text is None:
            
            initial_search_text = 'search tags'
            
        
        if example_search_text is None:
            
            example_search_text = 'blue_eyes blonde_hair'
            
        
        HydrusSerialisable.SerialisableBaseNamed.__init__( self, name )
        
        self._gallery_url_generator_key = gug_key
        self._url_template = url_template
        self._replacement_phrase = replacement_phrase
        self._search_terms_separator = search_terms_separator
        self._initial_search_text = initial_search_text
        self._example_search_text = example_search_text
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_gallery_url_generator_key = self._gallery_url_generator_key.encode( 'hex' )
        
        return ( serialisable_gallery_url_generator_key, self._url_template, self._replacement_phrase, self._search_terms_separator, self._initial_search_text, self._example_search_text )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_gallery_url_generator_key, self._url_template, self._replacement_phrase, self._search_terms_separator, self._initial_search_text, self._example_search_text ) = serialisable_info
        
        self._gallery_url_generator_key = serialisable_gallery_url_generator_key.decode( 'hex' )
        
    
    def GenerateGalleryURL( self, query_text ):
        
        if self._replacement_phrase == '':
            
            raise HydrusExceptions.GUGException( 'No replacement phrase!' )
            
        
        if self._replacement_phrase not in self._url_template:
            
            raise HydrusExceptions.GUGException( 'Replacement phrase not in URL template!' )
            
        
        ( first_part, second_part ) = self._url_template.split( self._replacement_phrase, 1 )
        
        search_phrase_seems_to_go_in_path = '?' not in first_part
        
        search_terms = query_text.split( ' ' )
        
        if search_phrase_seems_to_go_in_path:
            
            # encode this gubbins since requests won't be able to do it
            # this basically fixes e621 searches for 'male/female', which through some httpconf trickery are embedded in path but end up in a query, so need to be encoded right beforehand
            # we need ToByteString as urllib.quote can't handle unicode hiragana etc...
            
            encoded_search_terms = [ urllib.quote( HydrusData.ToByteString( search_term ), safe = '' ) for search_term in search_terms ]
            
        else:
            
            # when the separator is '+' but the permitted tags might be '6+girls', we run into fun internet land
            
            encoded_search_terms = []
            
            for search_term in search_terms:
                
                if self._search_terms_separator in search_term:
                    
                    search_term = urllib.quote( HydrusData.ToByteString( search_term ), safe = '' )
                    
                
                encoded_search_terms.append( search_term )
                
            
        
        try:
            
            search_phrase = self._search_terms_separator.join( encoded_search_terms )
            
            gallery_url = self._url_template.replace( self._replacement_phrase, search_phrase )
            
        except Exception as e:
            
            raise HydrusExceptions.GUGException( unicode( e ) )
            
        
        return gallery_url
        
    
    def GenerateGalleryURLs( self, query_text ):
        
        return ( self.GenerateGalleryURL( query_text ), )
        
    
    def GetExampleURL( self ):
        
        return self.GenerateGalleryURL( self._example_search_text )
        
    
    def GetExampleURLs( self ):
        
        return ( self.GetExampleURL(), )
        
    
    def GetGUGKey( self ):
        
        return self._gallery_url_generator_key
        
    
    def GetGUGKeyAndName( self ):
        
        return ( self._gallery_url_generator_key, self._name )
        
    
    def GetInitialSearchText( self ):
        
        return self._initial_search_text
        
    
    def GetSafeSummary( self ):
        
        return 'Downloader "' + self._name + '" - ' + ConvertURLIntoDomain( self.GetExampleURL() )
        
    
    def GetURLTemplateVariables( self ):
        
        return ( self._url_template, self._replacement_phrase, self._search_terms_separator, self._example_search_text )
        
    
    def SetGUGKeyAndName( self, gug_key_and_name ):
        
        ( gug_key, name ) = gug_key_and_name
        
        self._gallery_url_generator_key = gug_key
        self._name = name
        
    
    def IsFunctional( self ):
        
        try:
            
            example_url = self.GetExampleURL()
            
            ( url_type, match_name, can_parse ) = HG.client_controller.network_engine.domain_manager.GetURLParseCapability( example_url )
            
        except:
            
            return False
            
        
        return can_parse
        
    
    def RegenerateGUGKey( self ):
        
        self._gallery_url_generator_key = HydrusData.GenerateKey()
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_GALLERY_URL_GENERATOR ] = GalleryURLGenerator

class NestedGalleryURLGenerator( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_NESTED_GALLERY_URL_GENERATOR
    SERIALISABLE_NAME = 'Nested Gallery URL Generator'
    SERIALISABLE_VERSION = 1
    
    def __init__( self, name, gug_key = None, initial_search_text = None, gug_keys_and_names = None ):
        
        if gug_key is None:
            
            gug_key = HydrusData.GenerateKey()
            
        
        if initial_search_text is None:
            
            initial_search_text = 'search tags'
            
        
        if gug_keys_and_names is None:
            
            gug_keys_and_names = []
            
        
        HydrusSerialisable.SerialisableBaseNamed.__init__( self, name )
        
        self._gallery_url_generator_key = gug_key
        self._initial_search_text = initial_search_text
        self._gug_keys_and_names = gug_keys_and_names
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_gug_key = self._gallery_url_generator_key.encode( 'hex' )
        serialisable_gug_keys_and_names = [ ( gug_key.encode( 'hex' ), gug_name ) for ( gug_key, gug_name ) in self._gug_keys_and_names ]
        
        return ( serialisable_gug_key, self._initial_search_text, serialisable_gug_keys_and_names )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_gug_key, self._initial_search_text, serialisable_gug_keys_and_names ) = serialisable_info
        
        self._gallery_url_generator_key = serialisable_gug_key.decode( 'hex' )
        self._gug_keys_and_names = [ ( gug_key.decode( 'hex' ), gug_name ) for ( gug_key, gug_name ) in serialisable_gug_keys_and_names ]
        
    
    def GenerateGalleryURLs( self, query_text ):
        
        gallery_urls = []
        
        for gug_key_and_name in self._gug_keys_and_names:
            
            gug = HG.client_controller.network_engine.domain_manager.GetGUG( gug_key_and_name )
            
            if gug is not None:
                
                gallery_urls.append( gug.GenerateGalleryURL( query_text ) )
                
            
        
        return gallery_urls
        
    
    def GetExampleURLs( self ):
        
        example_urls = []
        
        for gug_key_and_name in self._gug_keys_and_names:
            
            gug = HG.client_controller.network_engine.domain_manager.GetGUG( gug_key_and_name )
            
            if gug is not None:
                
                example_urls.append( gug.GetExampleURL() )
                
            
        
        return example_urls
        
    
    def GetGUGKey( self ):
        
        return self._gallery_url_generator_key
        
    
    def GetGUGKeys( self ):
        
        return [ gug_key for ( gug_key, gug_name ) in self._gug_keys_and_names ]
        
    
    def GetGUGKeysAndNames( self ):
        
        return list( self._gug_keys_and_names )
        
    
    def GetGUGKeyAndName( self ):
        
        return ( self._gallery_url_generator_key, self._name )
        
    
    def GetGUGNames( self ):
        
        return [ gug_name for ( gug_key, gug_name ) in self._gug_keys_and_names ]
        
    
    def GetInitialSearchText( self ):
        
        return self._initial_search_text
        
    
    def GetSafeSummary( self ):
        
        return 'Nested downloader "' + self._name + '" - ' + ', '.join( ( name for ( gug_key, name ) in self._gug_keys_and_names ) )
        
    
    def IsFunctional( self ):
        
        for gug_key_and_name in self._gug_keys_and_names:
            
            gug = HG.client_controller.network_engine.domain_manager.GetGUG( gug_key_and_name )
            
            if gug is not None:
                
                if gug.IsFunctional():
                    
                    return True
                    
                
            
        
        return False
        
    
    def RegenerateGUGKey( self ):
        
        self._gallery_url_generator_key = HydrusData.GenerateKey()
        
    
    def RepairGUGs( self, available_gugs ):
        
        available_keys_to_gugs = { gug.GetGUGKey() : gug for gug in available_gugs }
        available_names_to_gugs = { gug.GetName() : gug for gug in available_gugs }
        
        good_gug_keys_and_names = []
        
        for ( gug_key, gug_name ) in self._gug_keys_and_names:
            
            if gug_key in available_keys_to_gugs:
                
                gug = available_keys_to_gugs[ gug_key ]
                
            elif gug_name in available_names_to_gugs:
                
                gug = available_names_to_gugs[ gug_name ]
                
            else:
                
                continue
                
            
            good_gug_keys_and_names.append( ( gug.GetGUGKey(), gug.GetName() ) )
            
        
        self._gug_keys_and_names = good_gug_keys_and_names
        
    
    def SetGUGKeyAndName( self, gug_key_and_name ):
        
        ( gug_key, name ) = gug_key_and_name
        
        self._gallery_url_generator_key = gug_key
        self._name = name
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_NESTED_GALLERY_URL_GENERATOR ] = NestedGalleryURLGenerator

class URLMatch( HydrusSerialisable.SerialisableBaseNamed ):
    
    SERIALISABLE_TYPE = HydrusSerialisable.SERIALISABLE_TYPE_URL_MATCH
    SERIALISABLE_NAME = 'URL Class'
    SERIALISABLE_VERSION = 6
    
    def __init__( self, name, url_match_key = None, url_type = None, preferred_scheme = 'https', netloc = 'hostname.com', match_subdomains = False, keep_matched_subdomains = False, path_components = None, parameters = None, api_lookup_converter = None, can_produce_multiple_files = False, should_be_associated_with_files = True, gallery_index_type = None, gallery_index_identifier = None, gallery_index_delta = 1, example_url = 'https://hostname.com/post/page.php?id=123456&s=view' ):
        
        if url_match_key is None:
            
            url_match_key = HydrusData.GenerateKey()
            
        
        if url_type is None:
            
            url_type = HC.URL_TYPE_POST
            
        
        if path_components is None:
            
            path_components = []
            
            path_components.append( ( ClientParsing.StringMatch( match_type = ClientParsing.STRING_MATCH_FIXED, match_value = 'post', example_string = 'post' ), None ) )
            path_components.append( ( ClientParsing.StringMatch( match_type = ClientParsing.STRING_MATCH_FIXED, match_value = 'page.php', example_string = 'page.php' ), None ) )
            
        
        if parameters is None:
            
            parameters = {}
            
            parameters[ 's' ] = ( ClientParsing.StringMatch( match_type = ClientParsing.STRING_MATCH_FIXED, match_value = 'view', example_string = 'view' ), None )
            parameters[ 'id' ] = ( ClientParsing.StringMatch( match_type = ClientParsing.STRING_MATCH_FLEXIBLE, match_value = ClientParsing.NUMERIC, example_string = '123456' ), None )
            parameters[ 'page' ] = ( ClientParsing.StringMatch( match_type = ClientParsing.STRING_MATCH_FLEXIBLE, match_value = ClientParsing.NUMERIC, example_string = '1' ), '1' )
            
        
        if api_lookup_converter is None:
            
            api_lookup_converter = ClientParsing.StringConverter( example_string = 'https://hostname.com/post/page.php?id=123456&s=view' )
            
        
        # if the args are not serialisable stuff, lets overwrite here
        
        path_components = HydrusSerialisable.SerialisableList( path_components )
        parameters = HydrusSerialisable.SerialisableDictionary( parameters )
        
        HydrusSerialisable.SerialisableBaseNamed.__init__( self, name )
        
        self._url_match_key = url_match_key
        self._url_type = url_type
        self._preferred_scheme = preferred_scheme
        self._netloc = netloc
        
        self._match_subdomains = match_subdomains
        self._keep_matched_subdomains = keep_matched_subdomains
        self._can_produce_multiple_files = can_produce_multiple_files
        self._should_be_associated_with_files = should_be_associated_with_files
        
        self._path_components = path_components
        self._parameters = parameters
        self._api_lookup_converter = api_lookup_converter
        
        self._gallery_index_type = gallery_index_type
        self._gallery_index_identifier = gallery_index_identifier
        self._gallery_index_delta = gallery_index_delta
        
        self._example_url = example_url
        
    
    def _ClipNetLoc( self, netloc ):
        
        if self._keep_matched_subdomains:
            
            # for domains like artistname.website.com, where removing the subdomain may break the url, we leave it alone
            
            pass
            
        else:
            
            # for domains like mediaserver4.website.com, where multiple subdomains serve the same content as the larger site
            
            if not DomainEqualsAnotherForgivingWWW( netloc, self._netloc ):
                
                netloc = self._netloc
                
            
        
        return netloc
        
    
    def _ClipAndFleshOutPath( self, path, allow_clip = True ):
        
        # /post/show/1326143/akunim-anthro-armband-armwear-clothed-clothing-fem
        
        while path.startswith( '/' ):
            
            path = path[ 1 : ]
            
        
        # post/show/1326143/akunim-anthro-armband-armwear-clothed-clothing-fem
        
        path_components = path.split( '/' )
        
        if allow_clip or len( path_components ) < len( self._path_components ):
            
            clipped_path_components = []
            
            for ( index, ( string_match, default ) ) in enumerate( self._path_components ):
                
                if len( path_components ) > index: # the given path has the value
                    
                    clipped_path_component = path_components[ index ]
                    
                elif default is not None:
                    
                    clipped_path_component = default
                    
                else:
                    
                    raise HydrusExceptions.URLMatchException( 'Could not clip path--given url appeared to be too short!' )
                    
                
                clipped_path_components.append( clipped_path_component )
                
            
            path = '/'.join( clipped_path_components )
            
        
        # post/show/1326143
        
        if len( path ) > 0:
            
            path = '/' + path
            
        
        # /post/show/1326143
        
        return path
        
    
    def _ClipAndFleshOutQuery( self, query, allow_clip = True ):
        
        query_dict = ConvertQueryTextToDict( query )
        
        if allow_clip:
            
            query_dict = { key : value for ( key, value ) in query_dict.items() if key in self._parameters }
            
        
        for ( key, ( string_match, default ) ) in self._parameters.items():
            
            if key not in query_dict:
                
                if default is None:
                    
                    raise HydrusExceptions.URLMatchException( 'Could not flesh out query--no default for ' + key + ' defined!' )
                    
                else:
                    
                    query_dict[ key ] = default
                    
                
            
        
        query = ConvertQueryDictToText( query_dict )
        
        return query
        
    
    def _GetSerialisableInfo( self ):
        
        serialisable_url_match_key = self._url_match_key.encode( 'hex' )
        serialisable_path_components = [ ( string_match.GetSerialisableTuple(), default ) for ( string_match, default ) in self._path_components ]
        serialisable_parameters = [ ( key, ( string_match.GetSerialisableTuple(), default ) ) for ( key, ( string_match, default ) ) in self._parameters.items() ]
        serialisable_api_lookup_converter = self._api_lookup_converter.GetSerialisableTuple()
        
        return ( serialisable_url_match_key, self._url_type, self._preferred_scheme, self._netloc, self._match_subdomains, self._keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, self._can_produce_multiple_files, self._should_be_associated_with_files, self._gallery_index_type, self._gallery_index_identifier, self._gallery_index_delta, self._example_url )
        
    
    def _InitialiseFromSerialisableInfo( self, serialisable_info ):
        
        ( serialisable_url_match_key, self._url_type, self._preferred_scheme, self._netloc, self._match_subdomains, self._keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, self._can_produce_multiple_files, self._should_be_associated_with_files, self._gallery_index_type, self._gallery_index_identifier, self._gallery_index_delta, self._example_url ) = serialisable_info
        
        self._url_match_key = serialisable_url_match_key.decode( 'hex' )
        self._path_components = [ ( HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match ), default ) for ( serialisable_string_match, default ) in serialisable_path_components ]
        self._parameters = { key : ( HydrusSerialisable.CreateFromSerialisableTuple( serialisable_string_match ), default ) for ( key, ( serialisable_string_match, default ) ) in serialisable_parameters }
        self._api_lookup_converter = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_api_lookup_converter )
        
    
    def _UpdateSerialisableInfo( self, version, old_serialisable_info ):
        
        if version == 1:
            
            ( url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, example_url ) = old_serialisable_info
            
            url_match_key = HydrusData.GenerateKey()
            
            serialisable_url_match_key = url_match_key.encode( 'hex' )
            
            api_lookup_converter = ClientParsing.StringConverter( example_string = example_url )
            
            serialisable_api_lookup_converter = api_lookup_converter.GetSerialisableTuple()
            
            new_serialisable_info = ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, example_url )
            
            return ( 2, new_serialisable_info )
            
        
        if version == 2:
            
            ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, example_url ) = old_serialisable_info
            
            if url_type in ( HC.URL_TYPE_FILE, HC.URL_TYPE_POST ):
                
                should_be_associated_with_files = True
                
            else:
                
                should_be_associated_with_files = False
                
            
            new_serialisable_info = ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, should_be_associated_with_files, example_url )
            
            return ( 3, new_serialisable_info )
            
        
        if version == 3:
            
            ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, should_be_associated_with_files, example_url ) = old_serialisable_info
            
            can_produce_multiple_files = False
            
            new_serialisable_info = ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, can_produce_multiple_files, should_be_associated_with_files, example_url )
            
            return ( 4, new_serialisable_info )
            
        
        if version == 4:
            
            ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, can_produce_multiple_files, should_be_associated_with_files, example_url ) = old_serialisable_info
            
            gallery_index_type = None
            gallery_index_identifier = None
            gallery_index_delta = 1
            
            new_serialisable_info = ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, can_produce_multiple_files, should_be_associated_with_files, gallery_index_type, gallery_index_identifier, gallery_index_delta, example_url )
            
            return ( 5, new_serialisable_info )
            
        
        if version == 5:
            
            ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, can_produce_multiple_files, should_be_associated_with_files, gallery_index_type, gallery_index_identifier, gallery_index_delta, example_url ) = old_serialisable_info
            
            path_components = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_path_components )
            parameters = HydrusSerialisable.CreateFromSerialisableTuple( serialisable_parameters )
            
            path_components = [ ( value, None ) for value in path_components ]
            parameters = { key : ( value, None ) for ( key, value ) in parameters.items() }
            
            serialisable_path_components = [ ( string_match.GetSerialisableTuple(), default ) for ( string_match, default ) in path_components ]
            serialisable_parameters = [ ( key, ( string_match.GetSerialisableTuple(), default ) ) for ( key, ( string_match, default ) ) in parameters.items() ]
            
            new_serialisable_info = ( serialisable_url_match_key, url_type, preferred_scheme, netloc, match_subdomains, keep_matched_subdomains, serialisable_path_components, serialisable_parameters, serialisable_api_lookup_converter, can_produce_multiple_files, should_be_associated_with_files, gallery_index_type, gallery_index_identifier, gallery_index_delta, example_url )
            
            return ( 6, new_serialisable_info )
            
        
    
    def CanGenerateNextGalleryPage( self ):
        
        if self._url_type == HC.URL_TYPE_GALLERY:
            
            if self._gallery_index_type is not None:
                
                return True
                
            
        
        return False
        
    
    def CanReferToMultipleFiles( self ):
        
        is_a_gallery_page = self._url_type in ( HC.URL_TYPE_GALLERY, HC.URL_TYPE_WATCHABLE )
        
        is_a_multipost_post_page = self._url_type == HC.URL_TYPE_POST and self._can_produce_multiple_files
        
        return is_a_gallery_page or is_a_multipost_post_page
        
    
    def ClippingIsAppropriate( self ):
        
        return self._should_be_associated_with_files or self.UsesAPIURL()
        
    
    def GetAPIURL( self, url = None ):
        
        if url is None:
            
            url = self._example_url
            
        
        url = self.Normalise( url )
        
        return self._api_lookup_converter.Convert( url )
        
    
    def GetDomain( self ):
        
        return ConvertDomainIntoSecondLevelDomain( HydrusData.ToByteString( self._netloc ) )
        
    
    def GetExampleURL( self ):
        
        return self._example_url
        
    
    def GetGalleryIndexValues( self ):
        
        return ( self._gallery_index_type, self._gallery_index_identifier, self._gallery_index_delta )
        
    
    def GetMatchKey( self ):
        
        return self._url_match_key
        
    
    def GetNextGalleryPage( self, url ):
        
        url = self.Normalise( url )
        
        p = urlparse.urlparse( url )
        
        scheme = p.scheme
        netloc = p.netloc
        path = p.path
        query = p.query
        params = ''
        fragment = ''
        
        if self._gallery_index_type == GALLERY_INDEX_TYPE_PATH_COMPONENT:
            
            page_index_path_component_index = self._gallery_index_identifier
            
            while path.startswith( '/' ):
                
                path = path[ 1 : ]
                
            
            path_components = path.split( '/' )
            
            try:
                
                page_index = path_components[ page_index_path_component_index ]
                
            except IndexError:
                
                raise HydrusExceptions.URLMatchException( 'Could not generate next gallery page--not enough path components!' )
                
            
            try:
                
                page_index = int( page_index )
                
            except:
                
                raise HydrusExceptions.URLMatchException( 'Could not generate next gallery page--index component was not an integer!' )
                
            
            path_components[ page_index_path_component_index ] = str( page_index + self._gallery_index_delta )
            
            path = '/' + '/'.join( path_components )
            
        elif self._gallery_index_type == GALLERY_INDEX_TYPE_PARAMETER:
            
            page_index_name = self._gallery_index_identifier
            
            query_dict = ConvertQueryTextToDict( query )
            
            if page_index_name not in query_dict:
                
                raise HydrusExceptions.URLMatchException( 'Could not generate next gallery page--did not find ' + str( self._gallery_index_identifier ) + ' in parameters!' )
                
            
            page_index = query_dict[ page_index_name ]
            
            try:
                
                page_index = int( page_index )
                
            except:
                
                raise HydrusExceptions.URLMatchException( 'Could not generate next gallery page--index component was not an integer!' )
                
            
            query_dict[ page_index_name ] = page_index + self._gallery_index_delta
            
            query = ConvertQueryDictToText( query_dict )
            
        else:
            
            raise NotImplementedError( 'Did not understand the next gallery page rules!' )
            
        
        r = urlparse.ParseResult( scheme, netloc, path, params, query, fragment )
        
        return r.geturl()
        
    
    def GetSafeSummary( self ):
        
        return 'URL Class "' + self._name + '" - ' + ConvertURLIntoDomain( self.GetExampleURL() )
        
    
    def GetURLType( self ):
        
        return self._url_type
        
    
    def IsGalleryURL( self ):
        
        return self._url_type == HC.URL_TYPE_GALLERY
        
    
    def IsParsable( self ):
        
        return self._url_type in ( HC.URL_TYPE_POST, HC.URL_TYPE_GALLERY, HC.URL_TYPE_WATCHABLE )
        
    
    def IsPostURL( self ):
        
        return self._url_type == HC.URL_TYPE_POST
        
    
    def IsWatchableURL( self ):
        
        return self._url_type == HC.URL_TYPE_WATCHABLE
        
    
    def Matches( self, url ):
        
        try:
            
            self.Test( url )
            
            return True
            
        except HydrusExceptions.URLMatchException:
            
            return False
            
        
    
    def Normalise( self, url ):
        
        p = urlparse.urlparse( url )
        
        scheme = self._preferred_scheme
        params = ''
        fragment = ''
        
        if self.ClippingIsAppropriate():
            
            netloc = self._ClipNetLoc( p.netloc )
            path = self._ClipAndFleshOutPath( p.path )
            query = self._ClipAndFleshOutQuery( p.query )
            
        else:
            
            netloc = p.netloc
            path = self._ClipAndFleshOutPath( p.path, allow_clip = False )
            query = self._ClipAndFleshOutQuery( p.query, allow_clip = False )
            
        
        r = urlparse.ParseResult( scheme, netloc, path, params, query, fragment )
        
        return r.geturl()
        
    
    def RefersToOneFile( self ):
        
        is_a_direct_file_page = self._url_type == HC.URL_TYPE_FILE
        
        is_a_single_file_post_page = self._url_type == HC.URL_TYPE_POST and not self._can_produce_multiple_files
        
        return is_a_direct_file_page or is_a_single_file_post_page
        
    
    def RegenerateMatchKey( self ):
        
        self._url_match_key = HydrusData.GenerateKey()
        
    
    def SetExampleURL( self, example_url ):
        
        self._example_url = example_url
        
    
    def SetMatchKey( self, match_key ):
        
        self._url_match_key = match_key
        
    
    def ShouldAssociateWithFiles( self ):
        
        return self._should_be_associated_with_files
        
    
    def Test( self, url ):
        
        p = urlparse.urlparse( url )
        
        if self._match_subdomains:
            
            if p.netloc != self._netloc and not p.netloc.endswith( '.' + self._netloc ):
                
                raise HydrusExceptions.URLMatchException( p.netloc + ' (potentially excluding subdomains) did not match ' + self._netloc )
                
            
        else:
            
            if not DomainEqualsAnotherForgivingWWW( p.netloc, self._netloc ):
                
                raise HydrusExceptions.URLMatchException( p.netloc + ' did not match ' + self._netloc )
                
            
        
        url_path = p.path
        
        while url_path.startswith( '/' ):
            
            url_path = url_path[ 1 : ]
            
        
        url_path_components = url_path.split( '/' )
        
        for ( index, ( string_match, default ) ) in enumerate( self._path_components ):
            
            if len( url_path_components ) > index:
                
                url_path_component = url_path_components[ index ]
                
                try:
                    
                    string_match.Test( url_path_component )
                    
                except HydrusExceptions.StringMatchException as e:
                    
                    raise HydrusExceptions.URLMatchException( HydrusData.ToUnicode( e ) )
                    
                
            elif default is None:
                
                raise HydrusExceptions.URLMatchException( url_path + ' did not have enough of the required path components!' )
                
            
        
        url_parameters = ConvertQueryTextToDict( p.query )
        
        for ( key, ( string_match, default ) ) in self._parameters.items():
            
            if key not in url_parameters:
                
                if default is None:
                    
                    raise HydrusExceptions.URLMatchException( key + ' not found in ' + p.query )
                    
                else:
                    
                    continue
                    
                
            
            value = url_parameters[ key ]
            
            try:
                
                string_match.Test( value )
                
            except HydrusExceptions.StringMatchException as e:
                
                raise HydrusExceptions.URLMatchException( HydrusData.ToUnicode( e ) )
                
            
        
    
    def ToTuple( self ):
        
        return ( self._url_type, self._preferred_scheme, self._netloc, self._match_subdomains, self._keep_matched_subdomains, self._path_components, self._parameters, self._api_lookup_converter, self._can_produce_multiple_files, self._should_be_associated_with_files, self._example_url )
        
    
    def UsesAPIURL( self ):
        
        return self._api_lookup_converter.MakesChanges()
        
    
HydrusSerialisable.SERIALISABLE_TYPES_TO_OBJECT_TYPES[ HydrusSerialisable.SERIALISABLE_TYPE_URL_MATCH ] = URLMatch
