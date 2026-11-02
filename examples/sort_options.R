# Independent source-reading ordering witness for the original SORT fixtures.
# Repository/Base-R policy evidence for maintainers, not a live SAS capture.
script <- sub('^--file=', '', grep('^--file=', commandArgs(), value=TRUE)[1L])
source(file.path(dirname(script), 'character_input.R'))

ascii_compare <- function(left, right) {
  a <- as.integer(charToRaw(left)); b <- as.integer(charToRaw(right))
  width <- max(length(a),length(b)); length(a)<-width; length(b)<-width
  a[is.na(a)]<-32L; b[is.na(b)]<-32L
  unequal <- which(a!=b)
  if(!length(unequal))return(0L)
  if(a[unequal[1L]]<b[unequal[1L]])-1L else 1L
}
compare_rows <- function(left,right,keys,directions,schema) {
  for(i in seq_along(keys)) {
    name<-keys[i];a<-left[[name]];b<-right[[name]]
    if(schema[[name]]$type=='character') c<-ascii_compare(a,b)
    else if(is.na(a) && is.na(b))c<-0L
    else if(is.na(a))c<--1L
    else if(is.na(b))c<-1L
    else c<-if(a<b)-1L else if(a>b)1L else 0L
    if(directions[i])c<--c
    if(c!=0L)return(c)
  }
  0L
}
sort_table <- function(table,keys,directions,deduplicate) {
  check(length(table$schema)<=32L && length(table$rows)<=1000L)
  check(all(keys %in% names(table$schema)) && !anyDuplicated(keys))
  # Stable insertion uses only pairwise comparisons, independently of Python sort.
  ordinals<-integer()
  for(next_id in seq_along(table$rows)) {
    before<-length(ordinals)+1L
    for(position in seq_along(ordinals)) {
      if(compare_rows(table$rows[[next_id]],table$rows[[ordinals[position]]],keys,directions,table$schema)<0L) {
        before<-position;break
      }
    }
    ordinals<-append(ordinals,next_id,after=before-1L)
  }
  retained<-integer()
  for(i in seq_along(ordinals)) {
    if(!deduplicate || i==1L || compare_rows(table$rows[[ordinals[i-1L]]],table$rows[[ordinals[i]]],keys,directions,table$schema)!=0L)
      retained<-c(retained,ordinals[i])
  }
  list(table=list(schema=table$schema,rows=table$rows[retained]),ordinals=ordinals,retained=retained)
}
execute_sort_source <- function(source_text) {
  statements<-scan_source(source_text);position<-1L;tables<-list();events<-character()
  physical<-observations<-attempts<-outputs<-steps<-sorts<-0L
  while(position<=length(statements)) {
    steps<-steps+1L;check(steps<=64L);text<-tolower(statements[[position]]$text)
    if(grepl('^data ',text)) {
      match<-regmatches(text,regexec('^data ([a-z_][a-z0-9_]{0,31})$',text))[[1L]]
      check(length(match)==2L && ordinary(match[2L]) && !match[2L] %in% names(tables))
      check(position+4L<=length(statements));body<-statements[position+seq_len(4L)]
      check(tolower(body[[1L]]$text)=='infile datalines dsd' && tolower(body[[3L]]$text)=='datalines4' && tolower(body[[4L]]$text)=='run')
      schema<-columns(body[[2L]]$text);records<-body[[3L]]$records
      check(!is.null(records) && length(records)<=1000L);rows<-list()
      for(record in records) {
        raw<-as.integer(charToRaw(record));check(length(raw)<=80L && all(raw>=32L & raw<=126L) && !grepl('[\x22\x27]',record))
        fields<-split_fields(record);check(length(fields)==length(schema));row<-list()
        for(i in seq_along(schema)) {
          value<-gsub('^ +| +$','',fields[i]);spec<-schema[[i]]
          if(spec$type=='character') {
            check(value!='.' && nchar(value,type='bytes')<=spec$length)
            row[[names(schema)[i]]]<-paste0(value,strrep(' ',spec$length-nchar(value,type='bytes')))
          } else row[[names(schema)[i]]]<-number(value)
        }
        rows[[length(rows)+1L]]<-row
      }
      tables[[match[2L]]]<-list(schema=schema,rows=rows)
      physical<-physical+length(records);observations<-observations+length(rows);attempts<-attempts+length(rows)+1L;outputs<-outputs+length(rows)
      position<-position+5L
    } else {
      check(position+2L<=length(statements))
      match<-regmatches(text,regexec('^proc sort data=([a-z_][a-z0-9_]{0,31}) out=([a-z_][a-z0-9_]{0,31})( nodupkey)?$',text))[[1L]]
      check(length(match)>=3L && ordinary(match[2L]) && ordinary(match[3L]) && match[2L] %in% names(tables) && !match[3L] %in% names(tables))
      input<-match[2L];output<-match[3L];deduplicate<-length(match)>=4L && nzchar(match[4L])
      check(tolower(statements[[position+2L]]$text)=='run')
      by<-tolower(statements[[position+1L]]$text);check(startsWith(by,'by '));words<-strsplit(substring(by,4L),' ',fixed=TRUE)[[1L]]
      table<-tables[[input]];keys<-character();directions<-logical()
      if(identical(words,'_all_')) {
        check(deduplicate);keys<-names(table$schema);directions<-rep(FALSE,length(keys));check(length(keys)>=1L)
      } else {
        i<-1L
        while(i<=length(words)) {
          desc<-words[i]=='descending';if(desc)i<-i+1L
          check(i<=length(words) && ordinary(words[i]));keys<-c(keys,words[i]);directions<-c(directions,desc);i<-i+1L
        }
        check(length(keys)>=1L && length(keys)<=8L)
      }
      check(!anyDuplicated(keys) && all(keys %in% names(table$schema)))
      sorted<-sort_table(table,keys,directions,deduplicate);tables[[output]]<-sorted$table
      events<-c(events,paste('SORT',statements[[position]]$line,input,output,
                           if(length(sorted$ordinals))paste(sorted$ordinals,collapse=',') else '-',
                           if(length(sorted$retained))paste(sorted$retained,collapse=',') else '-'))
      sorts<-sorts+1L;position<-position+3L
    }
  }
  check(length(tables)>0L && sorts>0L)
  list(tables=tables,accounting=c(statements=length(statements),physical_records=physical,observations=observations,attempts=attempts,outputs=outputs),events=events)
}
paths<-readLines(commandArgs(trailingOnly=TRUE)[1L],warn=FALSE)
for(i in seq_along(paths)) {
  cat('BEGIN ',i,'\n',sep='')
  answer<-tryCatch(execute_sort_source(paste(readLines(paths[i],warn=FALSE),collapse='\n')),error=function(e)NULL)
  if(is.null(answer))cat('REFUSED\n') else cat(paste(c('OK',render(answer),answer$events),collapse='\n'),'\n',sep='')
  cat('END\n')
}
