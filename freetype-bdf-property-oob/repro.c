#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_BDF_H

#include <stdio.h>
#include <stdlib.h>

int
main( int argc, char** argv )
{
  const char*      path = argc > 1 ? argv[1] : "poc.ttf";
  FILE*            stream;
  unsigned char*   font;
  long             font_size;
  FT_Library       library;
  FT_Face          face;
  BDF_PropertyRec  property;
  FT_Error         error;

  stream = fopen( path, "rb" );
  if ( !stream ||
       fseek( stream, 0, SEEK_END ) != 0 ||
       ( font_size = ftell( stream ) ) < 0 ||
       fseek( stream, 0, SEEK_SET ) != 0 )
    return 1;

  font = (unsigned char*)malloc( (size_t)font_size );
  if ( !font || fread( font, 1, (size_t)font_size, stream ) !=
                 (size_t)font_size )
    return 2;
  fclose( stream );

  if ( FT_Init_FreeType( &library ) != 0 )
    return 3;
  if ( FT_New_Memory_Face( library, font, font_size, 0, &face ) != 0 )
    return 4;
  if ( FT_Set_Pixel_Sizes( face, 0, 16 ) != 0 )
    return 5;

  fprintf( stderr, "y_ppem=%u\n", face->size->metrics.y_ppem );
  error = FT_Get_BDF_Property( face, "CHARSET_REGISTRY", &property );
  fprintf( stderr, "FT_Get_BDF_Property returned %d\n", error );

  FT_Done_Face( face );
  FT_Done_FreeType( library );
  free( font );
  return 0;
}
