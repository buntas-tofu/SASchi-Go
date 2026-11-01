# Independent finite source parser and numeric INVALUE witness.
# Repository policy evidence, not a native SAS interpreter or catalog writer.
check <- function(ok, message='outside bounded INVALUE/input witness') if(!isTRUE(ok))stop(message)
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ordinary <- function(x) length(x)==1L && !is.na(x) && grepl('^[a-z_][a-z0-9_]{0,31}$',x) &&
  !x %in% c('_null_','_n_','_error_','_all_','_numeric_','_character_','_temporary_',
            '_infile_','_file_','_ods_','_page_','_blankpage_')
custom_name <- function(x) ordinary(x) && nchar(x,type='bytes')<=31L && !grepl('[0-9]$',x) &&
  (x=='eval' || startsWith(x,'usr_'))
ascii <- function(x) all(as.integer(charToRaw(x))>=32L & as.integer(charToRaw(x))<=126L)
scan_source <- function(source) {
  chars<-strsplit(source,'',fixed=TRUE)[[1]]; n<-length(chars);at<-1L;line<-1L;first<-NULL
  buf<-'';statements<-list();quoted<-'';pending_space<-FALSE
  add<-function(ch) {if(pending_space && nzchar(buf))buf<<-paste0(buf,' ');pending_space<<-FALSE;buf<<-paste0(buf,ch)}
  while(at<=n) {
    ch<-chars[at]
    if(nzchar(quoted)) {
      buf<-paste0(buf,ch);if(ch=='\n')line<-line+1L
      if(ch==quoted) {
        if(at<n && chars[at+1L]==quoted) {buf<-paste0(buf,quoted);at<-at+2L;next}
        quoted<-''
      }
      at<-at+1L;next
    }
    if(ch=='/' && at<n && chars[at+1L]=='*') {
      depth<-1L;at<-at+2L
      while(at<=n && depth>0L) {
        if(at<n && chars[at]=='/' && chars[at+1L]=='*'){depth<-depth+1L;at<-at+2L}
        else if(at<n && chars[at]=='*' && chars[at+1L]=='/'){depth<-depth-1L;at<-at+2L}
        else {if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      }
      check(depth==0L);pending_space<-TRUE;next
    }
    if(!nzchar(buf) && (ch=='*' || (ch=='%' && at<n && chars[at+1L]=='*'))) {
      while(at<=n && chars[at]!=';'){if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      check(at<=n);at<-at+1L;next
    }
    if(ch %in% c(' ','\t','\r','\n')){pending_space<-TRUE;if(ch=='\n')line<-line+1L;at<-at+1L;next}
    if(ch==';') {
      at<-at+1L
      if(!nzchar(buf)){pending_space<-FALSE;next}
      item<-list(text=buf,line=first);buf<-'';first<-NULL;pending_space<-FALSE
      if(tolower(item$text)=='datalines') {
        while(at<=n && chars[at]!='\n'){check(chars[at] %in% c(' ','\r'));at<-at+1L}
        check(at<=n);at<-at+1L;line<-line+1L;records<-character();done<-FALSE
        while(at<=n) {
          record<-''
          while(at<=n && chars[at]!='\n'){record<-paste0(record,chars[at]);at<-at+1L}
          if(endsWith(record,'\r'))record<-substr(record,1L,nchar(record)-1L)
          if(trimws(record)==';'){check(record==';');item$terminator<-line;done<-TRUE
            if(at<=n){at<-at+1L;line<-line+1L};break}
          records<-c(records,record)
          if(at<=n){at<-at+1L;line<-line+1L}
        }
        check(done);item$records<-records
      }
      statements[[length(statements)+1L]]<-item;next
    }
    if(is.null(first))first<-line
    if(ch %in% c("'",'"')){if(nzchar(buf) && !endsWith(buf,' '))pending_space<-TRUE;add(ch);quoted<-ch}else add(ch)
    at<-at+1L
  }
  check(!nzchar(quoted) && !nzchar(buf));statements
}
parse_definition <- function(block) {
  check(length(block)==3L && tolower(block[[1L]]$text)=='proc format' && tolower(block[[3L]]$text)=='run')
  text<-block[[2L]]$text
  check(ascii(text));found<-regmatches(text,regexec('^[Ii][Nn][Vv][Aa][Ll][Uu][Ee] ([A-Za-z_][A-Za-z0-9_]{0,31}) (.+)$',text))[[1]]
  check(length(found)==3L);name<-tolower(found[2L]);check(custom_name(name));rest<-found[3L]
  keys<-character();values<-numeric()
  while(nzchar(trimws(rest))) {
    matched<-regmatches(rest,regexec("^ *(['\"])([^'\"&%]*)\\1 *= *([+-]?[0-9]+)(?= |['\"]|$)",rest,perl=TRUE))[[1]]
    check(length(matched)>=4L);raw<-matched[3L];literal<-matched[4L]
    digits<-sub('^[+-]','',literal);digits<-sub('^0+','',digits);if(!nzchar(digits))digits<-'0'
    check(nchar(digits)<=4L);value<-as.numeric(digits)*if(startsWith(literal,'-'))-1 else 1
    check(length(keys)<32L && nchar(raw,type='bytes')>=1L && nchar(raw,type='bytes')<=32L &&
          ascii(raw) && trimws(raw,whitespace=' ')==raw && !raw %in% keys && abs(value)<=1000)
    keys<-c(keys,raw);values<-c(values,value);rest<-substring(rest,nchar(matched[1L])+1L)
  }
  check(length(keys)>=1L)
  list(name=name,width=max(nchar(keys,type='bytes')),keys=keys,values=values,
       source_lines=c(block[[2L]]$line,block[[3L]]$line))
}
number_integer <- function(token) {
  check(nchar(token,type='bytes')>=1L && nchar(token,type='bytes')<=32L)
  check(grepl('^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$',token))
  pieces<-strsplit(token,'[eE]')[[1]];exponent<-if(length(pieces)==2L)as.numeric(pieces[2L])else 0
  check(is.finite(exponent) && abs(exponent)<=15)
  coefficient<-sub('^[+-]','',pieces[1L]);digits<-gsub('.','',coefficient,fixed=TRUE)
  check(nchar(digits)<=15L);dot<-regexpr('.',coefficient,fixed=TRUE)[1L]
  power<-exponent-if(dot>0L)nchar(coefficient)-dot else 0L
  digits<-sub('^0+','',digits);if(!nzchar(digits))return(0)
  if(power<0) {
    places<- -power;check(places<=nchar(digits) && endsWith(digits,strrep('0',places)))
    digits<-substring(digits,1L,nchar(digits)-places)
  } else {check(nchar(digits)+power<=4L);digits<-paste0(digits,strrep('0',power))}
  check(nchar(digits)<=4L);value<-as.numeric(digits)*if(startsWith(token,'-'))-1 else 1
  check(is.finite(value) && abs(value)<=1000);if(value==0)0 else value
}
apply_informat <- function(raw,definition) {
  token<-sub(' +$','',raw)
  check(nzchar(token) && !grepl('^ *\\.[A-Za-z_]? *$',token))
  at<-match(token,definition$keys)
  if(!is.na(at))return(definition$values[at])
  number_integer(trimws(token,whitespace=' '))
}
execute_definitions <- function(source) {
  st<-scan_source(source);registry<-list();at<-1L
  while(at<=length(st)) {
    check(at+2L<=length(st));definition<-parse_definition(st[at+0:2]);name<-definition$name
    check(length(registry)<8L && !name %in% names(registry));registry[[name]]<-definition;at<-at+3L
  }
  check(length(registry)>=1L);list(registry=registry,accounting=c(statements=length(st),definitions=length(registry)))
}
render_definitions <- function(result) {
  for(definition in result$registry) {
    cat('DEF ',definition$name,' ',definition$width,'\n',sep='')
    for(i in seq_along(definition$keys))cat('MAP ',hex(definition$keys[i]),' ',sprintf('%.0f',definition$values[i]),'\n',sep='')
    cat('ENDDEF\n')
  }
  cat('ACCOUNT ',paste(result$accounting,collapse=' '),'\n',sep='')
}
if(sys.nframe()==0L) {
  args<-commandArgs(trailingOnly=TRUE);check(length(args)==1L);paths<-readLines(args[1L],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('BEGIN ',i,'\n',sep='')
    tryCatch({text<-paste(readLines(paths[i],warn=FALSE),collapse='\n');render_definitions(execute_definitions(text));cat('OK\n')},error=function(e)cat('REFUSED\n'))
    cat('END\n')
  }
}
