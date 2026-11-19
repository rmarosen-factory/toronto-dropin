#!/usr/bin/osascript -l JavaScript
// Read a PDF with the Mac's own PDF reader, no extra software needed.
// Used when reading the EarlyON agencies' monthly calendars (see earlyon/README.md).
//
//   osascript -l JavaScript tools/pdf_read.js calendar.pdf out-folder [width-in-pixels]
//
// Writes out-folder/text.txt (the text of every page) and out-folder/page-N.png
// (a picture of each page, for calendars laid out as a grid).
ObjC.import('PDFKit');
ObjC.import('AppKit');

function run(argv) {
  if (argv.length < 2) return 'usage: pdf_read.js file.pdf out-folder [width]';
  // on a retina screen the pictures come out twice as wide as asked
  var src = argv[0], out = argv[1], width = +(argv[2] || 1000);
  var doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(src));
  if (doc.isNil()) return 'UNREADABLE: ' + src;
  $.NSFileManager.defaultManager.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(out, true, $(), null);
  var n = doc.pageCount, text = '';
  for (var i = 0; i < n; i++) {
    var page = doc.pageAtIndex(i);
    var s = page.string;
    text += '\n===== page ' + (i + 1) + ' of ' + n + ' =====\n' + (s.isNil() ? '' : ObjC.unwrap(s));
    var box = page.boundsForBox($.kPDFDisplayBoxMediaBox);
    var w = width, hgt = Math.round(box.size.height * width / box.size.width);
    if (page.rotation % 180 !== 0) hgt = Math.round(box.size.width * width / box.size.height);
    var thumb = page.thumbnailOfSizeForBox($.NSMakeSize(w, hgt), $.kPDFDisplayBoxMediaBox);
    // paint on white: some calendars have a see-through page background
    var img = $.NSImage.alloc.initWithSize($.NSMakeSize(w, hgt));
    img.lockFocus;
    $.NSColor.whiteColor.setFill;
    $.NSRectFill($.NSMakeRect(0, 0, w, hgt));
    thumb.drawInRectFromRectOperationFraction($.NSMakeRect(0, 0, w, hgt), $.NSZeroRect, $.NSCompositingOperationSourceOver, 1);
    img.unlockFocus;
    var rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
    rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $()).writeToFileAtomically(out + '/page-' + (i + 1) + '.png', true);
  }
  $(text).writeToFileAtomicallyEncodingError(out + '/text.txt', true, $.NSUTF8StringEncoding, null);
  return n + ' pages -> ' + out;
}
