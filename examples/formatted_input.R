# Independent complete-source INVALUE and fixed-position physical-record witness.
# Source this file to reuse its parser; no Python plan/helper is read.
script_path <- function() {
  for(frame in rev(sys.frames()))if(!is.null(frame$ofile))return(normalizePath(frame$ofile))
  arg<-grep('^--file=',commandArgs(),value=TRUE);check_path<-length(arg)==1L
  if(!check_path)stop('R source location unavailable')
  normalizePath(sub('^--file=','',arg))
}
source(file.path(dirname(script_path()),'numeric_invalue.R'))
parse_fields <- function(text,registry) {
  check(ascii(text));first<-regmatches(text,regexec('^[Ii][Nn][Pp][Uu][Tt] ([A-Za-z_][A-Za-z0-9_]{0,31}) +\\$( |$)',text))[[1]]
  check(length(first)>=2L);name<-tolower(first[2L]);check(ordinary(name))
  fields<-list(list(name=name,read='list_character'));schema<-list();schema[[name]]<-list(type='character',length=8L)
  rest<-substring(text,nchar(first[1L])+1L);custom<-FALSE
  while(nzchar(trimws(rest))) {
    # The first match may consume its separating blank; absolute pointers remain mandatory.
    m<-regmatches(rest,regexec('^ *@ *([0-9]{1,2}) +([A-Za-z_][A-Za-z0-9_]{0,31}) +(\\$ *([0-9]{1,2}) *\\.|([A-Za-z_][A-Za-z0-9_]{0,31}) *\\.)',rest))[[1]]
    check(length(m)>=6L);column<-as.integer(m[2L]);name<-tolower(m[3L])
    check(ordinary(name) && !name %in% names(schema) && column>=1L && column<=80L)
    if(nzchar(m[5L])) {width<-as.integer(m[5L]);check(width>=1L && width<=32L)
      field<-list(name=name,read='character',column=column,width=width);spec<-list(type='character',length=width)
    } else {informat<-tolower(m[6L]);check(custom_name(informat) && informat %in% names(registry))
      width<-registry[[informat]]$width;field<-list(name=name,read='numeric_informat',column=column,width=width,informat=informat)
      spec<-list(type='number',length=8L);custom<-TRUE}
    check(column+width-1L<=80L);schema[[name]]<-spec;fields[[length(fields)+1L]]<-field
    rest<-substring(rest,nchar(m[1L])+1L)
    check(!nzchar(rest) || grepl('^ ',rest))
  }
  check(custom && length(fields)>=2L && length(fields)<=32L);list(schema=schema,fields=fields)
}
execute_data_block <- function(block,registry) {
  check(length(block)==4L);header<-block[[1L]];input<-block[[2L]];data<-block[[3L]];run<-block[[4L]]
  text<-tolower(header$text);m<-regmatches(text,regexec('^data ([a-z_][a-z0-9_]{0,31})$',text))[[1]]
  check(length(m)==2L && ordinary(m[2L]) && length(registry)>0L);name<-m[2L]
  check(tolower(data$text)=='datalines' && tolower(run$text)=='run' && !is.null(data$records))
  parsed<-parse_fields(input$text,registry);schema<-parsed$schema;fields<-parsed$fields
  records<-data$records;check(length(records)<=1000L);rows<-list();trace<-list()
  for(i in seq_len(length(records)+1L)) {
    complete<-i<=length(records)
    trace[[length(trace)+1L]]<-list(kind='formatted_input',line=input$line,attempt=i,complete=complete)
    if(!complete)next
    record<-records[i]
    check(nchar(record,type='bytes')<=80L && ascii(record) && !grepl("['\";]",record))
    token<-regmatches(record,regexec('^ *([^ ]+)',record))[[1]];check(length(token)==2L && nchar(token[2L])<=8L && token[2L]!='.')
    row<-list();row[[fields[[1L]]$name]]<-paste0(token[2L],strrep(' ',8L-nchar(token[2L])))
    for(field in fields[-1L]) {
      check(nchar(record)>=field$column+field$width-1L);raw<-substring(record,field$column,field$column+field$width-1L)
      if(field$read=='character') {
        value<-sub('^ +','',raw);if(sub(' +$','',value)=='.')value<-''
        row[[field$name]]<-paste0(value,strrep(' ',field$width-nchar(value)))
      } else row[[field$name]]<-apply_informat(raw,registry[[field$informat]])
    }
    rows[[length(rows)+1L]]<-row
    trace[[length(trace)+1L]]<-list(kind='formatted_output',line=input$line,observation=i)
  }
  list(name=name,table=list(schema=schema,rows=rows),
       source_lines=c(header$line,input$line,data$line,data$terminator,run$line),trace=trace,
       accounting=c(producers=1L,physical_records=length(records),observations=length(rows),
                    attempts=length(rows)+1L,outputs=length(rows)))
}
execute_formatted <- function(source) {
  st<-scan_source(source);registry<-list();tables<-list();at<-1L
  totals<-c(producers=0L,physical_records=0L,observations=0L,attempts=0L,outputs=0L);trace<-list()
  while(at<=length(st)) {
    check(length(registry)+totals['producers']<64L);text<-tolower(st[[at]]$text)
    if(text=='proc format') {
      check(at+2L<=length(st));definition<-parse_definition(st[at+0:2]);name<-definition$name
      check(length(registry)<8L && !name %in% names(registry));registry[[name]]<-definition;at<-at+3L
    } else {
      check(at+3L<=length(st) && totals['producers']<8L)
      data<-execute_data_block(st[at+0:3],registry)
      check(!data$name %in% names(tables));tables[[data$name]]<-data$table
      totals<-totals+data$accounting;trace<-c(trace,data$trace);at<-at+4L
    }
  }
  check(length(registry)>=1L && totals['producers']>=1L)
  list(tables=tables,registry=registry,trace=trace,
       accounting=c(statements=length(st),definitions=length(registry),totals))
}
render <- function(result) {
  for(name in names(result$tables)) {
    table<-result$tables[[name]];cat('TABLE ',name,'\n',sep='')
    for(column in names(table$schema)){spec<-table$schema[[column]];cat('COL ',column,' ',spec$type,' ',spec$length,'\n',sep='')}
    for(row in table$rows) {
      values<-vapply(names(table$schema),function(column){value<-row[[column]]
        if(table$schema[[column]]$type=='character')paste0('C:',hex(value))else paste0('N:',sprintf('%.0f',value))},'')
      cat('ROW ',paste(values,collapse='|'),'\n',sep='')
    }
    cat('ENDTABLE\n')
  }
  for(event in result$trace) {
    if(event$kind=='formatted_input')cat('TRACE input ',event$line,' ',event$attempt,' ',if(event$complete)'1'else'0','\n',sep='')
    else cat('TRACE output ',event$line,' ',event$observation,'\n',sep='')
  }
  cat('ACCOUNT ',paste(result$accounting,collapse=' '),'\n',sep='')
}
if(sys.nframe()==0L) {
  args<-commandArgs(trailingOnly=TRUE);check(length(args)==1L);paths<-readLines(args[1L],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('BEGIN ',i,'\n',sep='')
    tryCatch({text<-paste(readLines(paths[i],warn=FALSE),collapse='\n');render(execute_formatted(text));cat('OK\n')},error=function(e)cat('REFUSED\n'))
    cat('END\n')
  }
}
