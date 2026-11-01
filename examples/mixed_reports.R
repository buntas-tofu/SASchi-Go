# Independent TITLE/PRINT source scheduler and logical report renderer.
# Reuses the independent first-party character DATA decoder in a private R environment.
args <- commandArgs(trailingOnly=TRUE)
script_arg <- grep('^--file=',commandArgs(),value=TRUE)
script_path <- if(length(script_arg)) sub('^--file=','',script_arg[1L]) else 'examples/mixed_reports.R'
base_dir <- dirname(normalizePath(script_path,mustWork=TRUE))
input <- new.env(parent=globalenv())
sys.source(file.path(base_dir,'character_input.R'),envir=input)
check <- function(x) if(!isTRUE(x)) stop('outside bounded mixed report witness')
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
canonical <- function(text) {
  cs<-strsplit(text,'',fixed=TRUE)[[1]];out<-'';q<-NULL;i<-1L;space<-FALSE
  while(i<=length(cs)) {
    c<-cs[i]
    if(!is.null(q)) {
      out<-paste0(out,c)
      if(c==q) {
        if(i<length(cs) && cs[i+1L]==q) {out<-paste0(out,q);i<-i+1L} else q<-NULL
      }
    } else if(c %in% c(' ','\t','\r','\n'))space<-TRUE
    else {
      if(space && nzchar(out))out<-paste0(out,' ')
      space<-FALSE;out<-paste0(out,c)
      if(c %in% c("'",'"'))q<-c
    }
    i<-i+1L
  }
  check(is.null(q));out
}
scan <- function(source) {
  cs<-strsplit(source,'',fixed=TRUE)[[1]];n<-length(cs);i<-1L;line<-1L;first<-NULL
  buffer<-'';q<-NULL;statements<-list()
  while(i<=n) {
    c<-cs[i]
    if(!is.null(q)) {
      buffer<-paste0(buffer,c)
      if(c==q) {
        if(i<n && cs[i+1L]==q) {buffer<-paste0(buffer,q);i<-i+1L} else q<-NULL
      }
      if(c=='\n')line<-line+1L;i<-i+1L;next
    }
    if(c=='/' && i<n && cs[i+1L]=='*') {
      depth<-1L;i<-i+2L
      while(i<=n && depth>0L) {
        if(i<n && cs[i]=='/' && cs[i+1L]=='*') {depth<-depth+1L;i<-i+2L}
        else if(i<n && cs[i]=='*' && cs[i+1L]=='/') {depth<-depth-1L;i<-i+2L}
        else {if(cs[i]=='\n')line<-line+1L;i<-i+1L}
      }
      check(depth==0L);buffer<-paste0(buffer,' ');next
    }
    if(!nzchar(trimws(buffer)) && (c=='*' || c=='%' && i<n && cs[i+1L]=='*')) {
      while(i<=n && cs[i]!=';') {if(cs[i]=='\n')line<-line+1L;i<-i+1L}
      check(i<=n);i<-i+1L;next
    }
    if(c==';') {
      text<-canonical(buffer);check(nzchar(text));check(all(as.integer(charToRaw(text))<128L))
      item<-list(text=text,line=first);buffer<-'';first<-NULL;i<-i+1L
      if(tolower(text)=='datalines4') {
        while(i<=n && cs[i]!='\n') {check(cs[i] %in% c(' ','\r'));i<-i+1L}
        check(i<=n);i<-i+1L;line<-line+1L;records<-character();done<-FALSE
        while(i<=n) {
          record<-''
          while(i<=n && cs[i]!='\n') {record<-paste0(record,cs[i]);i<-i+1L}
          if(endsWith(record,'\r'))record<-substr(record,1L,nchar(record)-1L)
          if(record==';;;;') {done<-TRUE;item$terminator<-line;break}
          records<-c(records,record)
          if(i<=n) {i<-i+1L;line<-line+1L}
        }
        check(done);item$records<-records
      }
      statements[[length(statements)+1L]]<-item;next
    }
    if(is.null(first) && !c %in% c(' ','\t','\r','\n'))first<-line
    if(c %in% c("'",'"'))q<-c
    buffer<-paste0(buffer,c);if(c=='\n')line<-line+1L;i<-i+1L
  }
  check(is.null(q) && !nzchar(trimws(buffer)));statements
}
quote_json <- function(value) {
  cs<-strsplit(value,'',fixed=TRUE)[[1]]
  escaped<-vapply(cs,function(ch)if(ch=='\\')'\\\\' else if(ch=='"')'\\"' else ch,'')
  paste0('"',paste(escaped,collapse=''),'"')
}
literal <- function(text) {
  check(nchar(text)>=2L);q<-substr(text,1L,1L);check(q %in% c("'",'"') && endsWith(text,q))
  inside<-substr(text,2L,nchar(text)-1L);remaining<-gsub(paste0(q,q),'',inside,fixed=TRUE)
  check(!grepl(q,remaining,fixed=TRUE));value<-gsub(paste0(q,q),q,inside,fixed=TRUE)
  check(nchar(value)>=1L && nchar(value)<=128L && nzchar(gsub(' ','',value,fixed=TRUE)))
  check(all(as.integer(charToRaw(value))>=32L & as.integer(charToRaw(value))<=126L) && !grepl('[&%]',value));value
}
execute <- function(source) {
  st<-scan(source);tables<-list();reports<-list();trace<-list();position<-1L;steps<-0L
  title<-NULL;title_count<-0L;print_count<-0L;producer_count<-0L
  physical<-attempts<-observations<-outputs<-printed<-set_count<-reset_count<-sort_count<-0L
  emit <- function(value)trace[[length(trace)+1L]]<<-list(type='string',value=value)
  while(position<=length(st)) {
    steps<-steps+1L;check(steps<=64L);text<-st[[position]]$text;lower<-tolower(text)
    if(grepl('^data ',lower)) {
      check(position+4L<=length(st));block<-st[position+0:4]
      check(tolower(block[[4L]]$text)=='datalines4' && tolower(block[[5L]]$text)=='run')
      chunk<-paste0(paste(vapply(block[1:4],function(x)paste0(x$text,';'),''),collapse='\n'),'\n',
                     paste(block[[4L]]$records,collapse='\n'),if(length(block[[4L]]$records))'\n' else '',
                     ';;;;\nrun;')
      decoded<-input$execute(chunk);check(length(decoded$tables)==1L);name<-names(decoded$tables)[1L]
      check(!name %in% names(tables));table<-decoded$tables[[name]];tables[[name]]<-table
      count<-length(table$rows);producer_count<-producer_count+1L;physical<-physical+length(block[[4L]]$records)
      observations<-observations+count;outputs<-outputs+count;attempts<-attempts+count+1L
      for(k in seq_len(count+1L)) {
        trace[[length(trace)+1L]]<-list(type='input',line=block[[3L]]$line,attempt=k,complete=k<=count)
        if(k<=count)trace[[length(trace)+1L]]<-list(type='output',line=block[[3L]]$line,observation=k)
      }
      position<-position+5L
    } else if(grepl('^title( |$)',lower)) {
      title_count<-title_count+1L;check(title_count<=32L)
      if(lower=='title') {title<-NULL;reset_count<-reset_count+1L;emit('title|reset')}
      else {title<-literal(substring(text,7L));set_count<-set_count+1L;emit(paste0('title|set|',hex(title)))}
      position<-position+1L
    } else if(grepl('^proc print ',lower)) {
      match<-regmatches(lower,regexec('^proc print data *= *([a-z_][a-z0-9_]{0,31})$',lower))[[1]]
      check(length(match)==2L && position+1L<=length(st) && tolower(st[[position+1L]]$text)=='run')
      name<-match[2L];check(input$ordinary(name) && name %in% names(tables));table<-tables[[name]]
      columns<-names(table$schema);check(length(columns)>=1L && length(columns)<=32L && !'obs' %in% columns)
      check(any(vapply(table$schema,function(x)x$type=='character',TRUE)) && length(table$rows)<=1000L)
      print_count<-print_count+1L;check(print_count<=2L);file<-sprintf('print_%02d.txt',print_count)
      lines<-character();emit(paste('mixed-print|input',name,length(table$rows),sep='|'))
      if(!is.null(title)) {lines<-paste0('TITLE: ',title);emit(paste0('mixed-print|title|',hex(lines)))}
      header<-paste(c('obs',columns),collapse=' ');check(nchar(header,type='bytes')<=1055L)
      lines<-c(lines,header);emit(paste0('mixed-print|header|',hex(header)))
      for(k in seq_along(table$rows)) {
        row<-table$rows[[k]];fields<-as.character(k)
        for(column in columns) {
          spec<-table$schema[[column]];value<-row[[column]]
          if(spec$type=='character') {
            check(spec$length>=1L && spec$length<=64L && nchar(value,type='bytes')==spec$length)
            value<-sub(' +$','',value);field<-quote_json(value)
          } else {
            check(spec$length==8L && (is.na(value) || is.finite(value) && value==trunc(value) && abs(value)<=2147483647))
            field<-if(is.na(value))'.' else if(value==0)'0' else sprintf('%.0f',value)
          }
          fields<-c(fields,field)
        }
        record<-paste(fields,collapse=' ');check(nchar(record,type='bytes')<=415L);lines<-c(lines,record)
        emit(paste0('mixed-print|row|',hex(record)))
      }
      report<-paste0(paste(lines,collapse='\n'),'\n');check(nchar(report,type='bytes')<=417056L)
      reports[[file]]<-report;emit(paste('mixed-print|output',file,nchar(report,type='bytes'),sep='|'))
      printed<-printed+length(table$rows);position<-position+2L
    } else {
      match<-regmatches(lower,regexec('^proc sort data *= *([a-z_][a-z0-9_]{0,31})( out *= *([a-z_][a-z0-9_]{0,31}))?( nodupkey)?$',lower))[[1]]
      check(length(match)>=2L && position+2L<=length(st));name<-match[2L]
      destination<-if(nzchar(match[4L]))match[4L] else name
      check(input$ordinary(name) && input$ordinary(destination) && name %in% names(tables))
      by<-tolower(st[[position+1L]]$text);check(grepl('^by ',by) && tolower(st[[position+2L]]$text)=='run')
      by<-strsplit(substring(by,4L),' ',fixed=TRUE)[[1]];table<-tables[[name]];check(all(by %in% names(table$schema)))
      rows<-table$rows;emit(paste('sort|input',name,length(rows),sep='|'))
      if(length(rows)) {
        values<-lapply(by,function(column)unlist(lapply(rows,function(row)row[[column]]),use.names=FALSE))
        rows<-rows[do.call(order,c(values,list(na.last=FALSE,method='radix')))]
        if(length(match)>=5L && nzchar(match[5L])) {
          keys<-vapply(rows,function(row)paste(vapply(by,function(column) {
            if(table$schema[[column]]$type=='character')paste0('C',hex(row[[column]]))
            else if(is.na(row[[column]]))'M' else paste0('N',sprintf('%.17g',row[[column]]))
          },''),collapse='|'),'')
          rows<-rows[!duplicated(keys)]
        }
      }
      tables[[destination]]<-list(schema=table$schema,rows=rows);sort_count<-sort_count+1L
      emit(paste('sort|output',destination,length(rows),sep='|'));position<-position+3L
    }
  }
  check(producer_count>=1L)
  list(tables=tables,reports=reports,trace=trace,accounting=c(statements=length(st),opaque_payloads=producer_count,
       steps=steps,physical_records=physical,input_attempts=attempts,observations=observations,outputs=outputs,
       sort_steps=sort_count,title_sets=set_count,title_resets=reset_count,print_steps=print_count,printed_rows=printed))
}
render <- function(answer) {
  table_wire<-input$render(list(tables=answer$tables,accounting=0))
  out<-table_wire[-length(table_wire)]
  for(name in names(answer$reports))out<-c(out,paste('REPORT',name,hex(answer$reports[[name]])))
  for(event in answer$trace) {
    if(event$type=='string')out<-c(out,paste('TRACE_STRING',hex(event$value)))
    else if(event$type=='input')out<-c(out,paste('TRACE_INPUT',event$line,event$attempt,if(event$complete)1 else 0))
    else out<-c(out,paste('TRACE_OUTPUT',event$line,event$observation))
  }
  c(out,paste('ACCOUNT',paste(answer$accounting,collapse=' ')))
}
if(sys.nframe()==0L) {
  paths<-readLines(args[1L],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('BEGIN ',i,'\n',sep='')
    result<-tryCatch(render(execute(paste(readLines(paths[i],warn=FALSE),collapse='\n'))),error=function(e)NULL)
    if(is.null(result))cat('REFUSED\n') else cat(paste(c('OK',result),collapse='\n'),'\n',sep='')
    cat('END\n')
  }
}
