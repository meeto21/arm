"""
Connection panel entries for client circuits. This includes a header entry
followed by an entry for each hop in the circuit. For instance:

89.188.20.246:42667    -->  217.172.182.26 (de)       General / Built     8.6m (CIRCUIT)
|  85.8.28.4 (se)               98FBC3B2B93897A78CDD797EF549E6B62C9A8523    1 / Guard
|  91.121.204.76 (fr)           546387D93F8D40CFF8842BB9D3A8EC477CEDA984    2 / Middle
+- 217.172.182.26 (de)          5CFA9EA136C0EA0AC096E5CEA7EB674F1207CF86    3 / Exit
"""

import curses

from interface.connections import entries, connEntry
from util import torTools, uiTools

# cached fingerprint -> (IP Address, ORPort) results
RELAY_INFO = {}

def getRelayInfo(fingerprint):
  """
  Provides the (IP Address, ORPort) tuple for the given relay. If the lookup
  fails then this returns ("192.168.0.1", "0").
  
  Arguments:
    fingerprint - relay to look up
  """
  
  if not fingerprint in RELAY_INFO:
    conn = torTools.getConn()
    failureResult = ("192.168.0.1", "0")
    
    nsEntry = conn.getConsensusEntry(fingerprint)
    if not nsEntry: return failureResult
    
    nsLineComp = nsEntry.split("\n")[0].split(" ")
    if len(nsLineComp) < 8: return failureResult
    
    RELAY_INFO[fingerprint] = (nsLineComp[6], nsLineComp[7])
  
  return RELAY_INFO[fingerprint]

class ClientEntry(connEntry.ConnectionEntry):
  def __init__(self, circuitID, status, purpose, path):
    connEntry.ConnectionEntry.__init__(self, "127.0.0.1", "0", "127.0.0.1", "0")
    
    self.circuitID = circuitID
    self.status = status
    
    # drops to lowercase except the first letter
    if len(purpose) >= 2:
      purpose = purpose[0].upper() + purpose[1:].lower()
    
    self.lines = [ClientHeaderLine(self.circuitID, purpose)]
    
    # Overwrites attributes of the initial line to make it more fitting as the
    # header for our listing.
    
    self.lines[0].baseType = connEntry.Category.CIRCUIT
    
    self.update(status, path)
  
  def update(self, status, path):
    """
    Our status and path can change over time if the circuit is still in the
    process of being built. Updates these attributs of our relay.
    
    Arguments:
      status - new status of the circuit
      path   - list of fingerprints for the series of relays involved in the
               circuit
    """
    
    self.status = status
    self.lines = [self.lines[0]]
    
    if status == "BUILT" and not self.lines[0].isBuilt:
      exitIp, exitORPort = getRelayInfo(path[-1])
      self.lines[0].setExit(exitIp, exitORPort, path[-1])
    
    for i in range(len(path)):
      relayFingerprint = path[i]
      relayIp, relayOrPort = getRelayInfo(relayFingerprint)
      
      if i == len(path) - 1:
        if status == "BUILT": placementType = "Exit"
        else: placementType = "Extending"
      elif i == 0: placementType = "Guard"
      else: placementType = "Middle"
      
      placementLabel = "%i / %s" % (i + 1, placementType)
      
      self.lines.append(ClientLine(relayIp, relayOrPort, relayFingerprint, placementLabel))
    
    self.lines[-1].isLast = True

class ClientHeaderLine(connEntry.ConnectionLine):
  """
  Initial line of a client entry. This has the same basic format as connection
  lines except that its etc field has circuit attributes.
  """
  
  def __init__(self, circuitID, purpose):
    connEntry.ConnectionLine.__init__(self, "127.0.0.1", "0", "0.0.0.0", "0", False, False)
    self.circuitID = circuitID
    self.purpose = purpose
    self.isBuilt = False
  
  def setExit(self, exitIpAddr, exitPort, exitFingerprint):
    connEntry.ConnectionLine.__init__(self, "127.0.0.1", "0", exitIpAddr, exitPort, False, False)
    self.isBuilt = True
    self.foreign.fingerprintOverwrite = exitFingerprint
  
  def getType(self):
    return connEntry.Category.CIRCUIT
  
  def getDestinationLabel(self, maxLength, includeLocale=False, includeHostname=False):
    if not self.isBuilt: return "Building..."
    return connEntry.ConnectionLine.getDestinationLabel(self, maxLength, includeLocale, includeHostname)
  
  def getEtcContent(self, width, listingType):
    """
    Attempts to provide all circuit related stats. Anything that can't be
    shown completely (not enough room) is dropped.
    """
    
    etcAttr = ["Purpose: %s" % self.purpose, "Circuit ID: %i" % self.circuitID]
    
    for i in range(len(etcAttr), -1, -1):
      etcLabel = ", ".join(etcAttr[:i])
      if len(etcLabel) <= width: return etcLabel
    
    return ""
  
  def getDetails(self, width):
    if not self.isBuilt:
      detailFormat = curses.A_BOLD | uiTools.getColor(connEntry.CATEGORY_COLOR[self.getType()])
      return [uiTools.DrawEntry("Building Circuit...", detailFormat)]
    else: return connEntry.ConnectionLine.getDetails(self, width)

class ClientLine(connEntry.ConnectionLine):
  """
  An inidividual hop in a circuit. This overwrites the displayed listing, but
  otherwise makes use of the ConnectionLine attributes (for the detail display,
  caching, etc).
  """
  
  def __init__(self, fIpAddr, fPort, fFingerprint, placementLabel):
    connEntry.ConnectionLine.__init__(self, "127.0.0.1", "0", fIpAddr, fPort)
    self.foreign.fingerprintOverwrite = fFingerprint
    self.placementLabel = placementLabel
    self.includePort = False
    
    # determines the sort of left hand bracketing we use
    self.isLast = False
  
  def getType(self):
    return connEntry.Category.CIRCUIT
  
  def getListingEntry(self, width, currentTime, listingType):
    """
    Provides the DrawEntry for this relay in the circuilt listing. Lines are
    composed of the following components:
      <bracket> <dst> <etc> <placement label>
    
    The dst and etc entries largely match their ConnectionEntry counterparts.
    
    Arguments:
      width       - maximum length of the line
      currentTime - the current unix time (ignored)
      listingType - primary attribute we're listing connections by
    """
    
    return entries.ConnectionPanelLine.getListingEntry(self, width, currentTime, listingType)
  
  def _getListingEntry(self, width, currentTime, listingType):
    lineFormat = uiTools.getColor(connEntry.CATEGORY_COLOR[self.getType()])
    
    # The required widths are the sum of the following:
    # bracketing (3 characters)
    # placementLabel (14 characters)
    # gap between etc and placement label (5 characters)
    
    if self.isLast: bracket = (curses.ACS_LLCORNER, curses.ACS_HLINE, ord(' '))
    else: bracket = (curses.ACS_VLINE, ord(' '), ord(' '))
    baselineSpace = len(bracket) + 14 + 5
    
    dst, etc = "", ""
    if listingType == entries.ListingType.IP_ADDRESS:
      # TODO: include hostname when that's available
      # dst width is derived as:
      # src (21) + dst (26) + divider (7) + right gap (2) - bracket (3) = 53 char
      dst = "%-53s" % self.getDestinationLabel(53, includeLocale = True)
      etc = self.getEtcContent(width - baselineSpace - len(dst), listingType)
    elif listingType == entries.ListingType.HOSTNAME:
      # min space for the hostname is 40 characters
      etc = self.getEtcContent(width - baselineSpace - 40, listingType)
      dstLayout = "%%-%is" % (width - baselineSpace - len(etc))
      dst = dstLayout % self.foreign.getHostname(self.foreign.getIpAddr())
    elif listingType == entries.ListingType.FINGERPRINT:
      # dst width is derived as:
      # src (9) + dst (40) + divider (7) + right gap (2) - bracket (3) = 55 char
      dst = "%-55s" % self.foreign.getFingerprint()
      etc = self.getEtcContent(width - baselineSpace - len(dst), listingType)
    else:
      # min space for the nickname is 50 characters
      etc = self.getEtcContent(width - baselineSpace - 50, listingType)
      dstLayout = "%%-%is" % (width - baselineSpace - len(etc))
      dst = dstLayout % self.foreign.getNickname()
    
    drawEntry = uiTools.DrawEntry("%-14s" % self.placementLabel, lineFormat)
    drawEntry = uiTools.DrawEntry(" " * (width - baselineSpace - len(dst) - len(etc) + 5), lineFormat, drawEntry)
    drawEntry = uiTools.DrawEntry(dst + etc, lineFormat, drawEntry)
    drawEntry = uiTools.DrawEntry(bracket, curses.A_NORMAL, drawEntry, lockFormat = True)
    return drawEntry

