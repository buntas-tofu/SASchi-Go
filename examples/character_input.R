# Independent complete-source interpreter for character-records-v1 plus SORT.
# This is a bounded repository witness, not a live SAS implementation.
ordinary <- function(x) length(x)==1L && !is.na(x) && grepl('^[a-z_][a-z0-9_]{0,31}$',x) &&
  !x %in% c('_null_','_n_','_error_','_all_','_numeric_','_character_','_temporary_',
             '_infile_','_file_','_ods_','_page_','_blankpage_')
check <- function(ok, message='outside bounded character input witness') if (!isTRUE(ok)) stop(message)
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
scan_source <- function(source) {
  chars <- strsplit(source,'',fixed=TRUE)[[1]]; n <- length(chars)
  at <- 1L; line <- 1L; first <- NULL; buf <- ''; statements <- list()
  while (at<=n) {
    ch <- chars[at]
    if (ch=='/' && at<n && chars[at+1L]=='*') {
      depth <- 1L; at <- at+2L
      while(at<=n && depth>0L) {
        if(at<n && chars[at]=='/' && chars[at+1L]=='*') {depth<-depth+1L;at<-at+2L}
        else if(at<n && chars[at]=='*' && chars[at+1L]=='/') {depth<-depth-1L;at<-at+2L}
        else {if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      }
      check(depth==0L); buf<-paste0(buf,' '); next
    }
    if(ch=='*' && !nzchar(trimws(buf))) {
      while(at<=n && chars[at]!=';') {if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      check(at<=n);at<-at+1L;next
    }
    if(ch==';') {
      text <- gsub('[ \t\r\n]+',' ',trimws(buf)); check(nzchar(text))
      check(all(as.integer(charToRaw(text))<128L))
      item <- list(text=text,line=first);at<-at+1L;buf<-'';first<-NULL
      if(tolower(text)=='datalines4') {
        while(at<=n && chars[at]!='\n') {check(chars[at]==' ' || chars[at]=='\r');at<-at+1L}
        check(at<=n);at<-at+1L;line<-line+1L;records<-character();done<-FALSE
        while(at<=n) {
          record<-''
          while(at<=n && chars[at]!='\n') {record<-paste0(record,chars[at]);at<-at+1L}
          if(endsWith(record,'\r'))record<-substr(record,1L,nchar(record)-1L)
          if(record==';;;;') {done<-TRUE;item$terminator<-line;break}
          records<-c(records,record)
          if(at<=n) {at<-at+1L;line<-line+1L}
        }
        check(done);item$records<-records
      }
      statements[[length(statements)+1L]]<-item;next
    }
    if(is.null(first) && !ch %in% c(' ','\t','\r','\n'))first<-line
    buf<-paste0(buf,ch);if(ch=='\n')line<-line+1L;at<-at+1L
  }
  check(!nzchar(trimws(buf)));statements
}
number <- function(token) {
  if(token=='' || token=='.')return(NA_real_)
  check(nchar(token,type='bytes')<=32L)
  check(grepl('^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$',token))
  parts<-strsplit(token,'[eE]')[[1]]; exponent<-if(length(parts)==2L)as.numeric(parts[2L]) else 0
  check(is.finite(exponent) && abs(exponent)<=15)
  base<-gsub('^[+-]','',parts[1L]);digits<-gsub('\\.','',base)
  check(nchar(digits)<=15L); dot<-regexpr('.',base,fixed=TRUE)[1L]
  scale<-(if(dot>0L)nchar(base)-dot else 0L)-exponent
  numerator<-as.numeric(digits)
  if(scale>0L)for(i in seq_len(scale)) {check(numerator%%5==0);numerator<-numerator/5}
  value<-as.numeric(token);check(is.finite(value) && abs(value)<=2147483647)
  if(value==0)0 else value
}
columns <- function(text) {
  check(grepl('^input ',tolower(text)));rest<-substring(text,7L);result<-list()
  while(nzchar(trimws(rest))) {
    found<-regexec('^ *([A-Za-z_][A-Za-z0-9_]{0,31})( *: *\\$ *([0-9]{1,2}) *\\.)?( |$)',rest)
    match<-regmatches(rest,found)[[1]];check(length(match)>0L)
    name<-tolower(match[2L]);check(ordinary(name) && !name %in% names(result))
    char<-length(match)>=4L && nzchar(match[4L]);width<-if(char)as.integer(match[4L]) else 8L
    check(!char || width>=1L && width<=64L)
    result[[name]]<-list(type=if(char)'character' else 'number',length=width)
    rest<-substring(rest,nchar(match[1L])+1L)
  }
  check(length(result)>=1L && length(result)<=32L && any(vapply(result,function(x)x$type=='character',TRUE)))
  result
}
split_fields <- function(record) {
  # Sentinel preserves all empty spans, including the final field.
  fields<-strsplit(paste0(record,',#'),',',fixed=TRUE)[[1]]
  fields[-length(fields)]
}
execute <- function(source) {
  st<-scan_source(source)
  tables<-list();position<-1L;steps<-0L;physical<-0L;observations<-0L;attempts<-0L;outputs<-0L
  while(position<=length(st)) {
    steps<-steps+1L;check(steps<=64L);text<-tolower(st[[position]]$text)
    if(grepl('^data ',text)) {
      match<-regmatches(text,regexec('^data ([a-z_][a-z0-9_]{0,31})$',text))[[1]]
      check(length(match)==2L && ordinary(match[2L]) && !match[2L] %in% names(tables));name<-match[2L]
      check(position+4L<=length(st));body<-st[position+seq_len(4L)]
      check(tolower(body[[1L]]$text)=='infile datalines dsd')
      schema<-columns(body[[2L]]$text)
      check(tolower(body[[3L]]$text)=='datalines4' && tolower(body[[4L]]$text)=='run')
      records<-body[[3L]]$records;check(!is.null(records) && length(records)<=1000L);rows<-list()
      for(record in records) {
        bytes<-as.integer(charToRaw(record))
        check(length(bytes)<=80L && all(bytes>=32L & bytes<=126L) && !grepl('[\x22\x27]',record))
        fields<-split_fields(record);check(length(fields)==length(schema));row<-list()
        for(i in seq_along(schema)) {
          field<-gsub('^ +| +$','',fields[i]);spec<-schema[[i]]
          if(spec$type=='character') {
            check(field!='.' && nchar(field,type='bytes')<=spec$length)
            row[[names(schema)[i]]]<-paste0(field,strrep(' ',spec$length-nchar(field,type='bytes')))
          } else row[[names(schema)[i]]]<-number(field)
        }
        rows[[length(rows)+1L]]<-row
      }
      tables[[name]]<-list(schema=schema,rows=rows)
      physical<-physical+length(records);observations<-observations+length(rows)
      attempts<-attempts+length(rows)+1L;outputs<-outputs+length(rows);position<-position+5L
    } else {
      match<-regmatches(text,regexec('^proc sort data=([a-z_][a-z0-9_]{0,31})( out=([a-z_][a-z0-9_]{0,31}))?( nodupkey)?$',text))[[1]]
      check(length(match)>=2L && position+2L<=length(st));input<-match[2L]
      check(ordinary(input) && input %in% names(tables));output<-if(nzchar(match[4L]))match[4L] else input
      check(ordinary(output));by<-tolower(st[[position+1L]]$text)
      check(tolower(st[[position+2L]]$text)=='run' && grepl('^by ',by));by<-strsplit(substring(by,4L),' ',fixed=TRUE)[[1]]
      table<-tables[[input]];check(length(by)>=1L && !anyDuplicated(by) && all(by %in% names(table$schema)))
      rows<-table$rows
      if(length(rows)>0L) {
        vectors<-lapply(by,function(name)unlist(lapply(rows,function(row)row[[name]]),use.names=FALSE))
        order_args<-c(vectors,list(na.last=FALSE,method='radix'));rows<-rows[do.call(order,order_args)]
        if(length(match)>=5L && nzchar(match[5L])) {
          keys<-vapply(rows,function(row)paste(vapply(by,function(name)if(is.na(row[[name]]))'M' else paste0('V',row[[name]]),''),collapse='|'),'')
          rows<-rows[!duplicated(keys)]
        }
      }
      tables[[output]]<-list(schema=table$schema,rows=rows);position<-position+3L
    }
  }
  list(tables=tables,accounting=c(statements=length(st),physical_records=physical,
       observations=observations,attempts=attempts,outputs=outputs))
}
render <- function(result) {
  out<-character()
  for(name in names(result$tables)) {
    table<-result$tables[[name]];out<-c(out,paste('TABLE',name))
    for(column in names(table$schema)) {spec<-table$schema[[column]];out<-c(out,paste('COL',column,spec$type,spec$length))}
    for(row in table$rows) {
      fields<-vapply(names(table$schema),function(column) {
        value<-row[[column]]
        if(table$schema[[column]]$type=='character')paste0('C:',hex(value))
        else if(is.na(value))'M' else paste0('N:',sprintf('%.17g',value))
      },'')
      out<-c(out,paste0('ROW ',paste(fields,collapse='|')))
    }
    out<-c(out,'ENDTABLE')
  }
  c(out,paste('ACCOUNT',paste(result$accounting,collapse=' ')))
}
if(sys.nframe()==0L) {
paths<-readLines(commandArgs(trailingOnly=TRUE)[1L],warn=FALSE)
for(i in seq_along(paths)) {
  cat('BEGIN ',i,'\n',sep='')
  answer<-tryCatch(render(execute(paste(readLines(paths[i],warn=FALSE),collapse='\n'))),error=function(e)NULL)
  if(is.null(answer))cat('REFUSED\n') else cat(paste(c('OK',answer),collapse='\n'),'\n',sep='')
  cat('END\n')
}
}
