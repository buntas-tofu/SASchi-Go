# Independent whole-source week callback and ordered/spanned REPORT witness.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2L,!file.exists(args[2]))
input_path <- args[1];output_path <- args[2]
script <- sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])
common <- file.path(dirname(normalizePath(script)),'format_oracle_common.R')
if(!file.exists(common)) common <- file.path('examples','format_oracle_common.R')
source(common)
invisible(Sys.setlocale('LC_TIME','C'));epoch <- as.Date('1960-01-01')
read_date <- function(text) {
 if(text=='.') return(NULL)
 months <- c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
 stopifnot(grepl('^[0-9]{2}[A-Za-z]{3}[0-9]{4}$',text))
 month <- match(toupper(substr(text,3,5)),months);stopifnot(!is.na(month))
 iso <- sprintf('%s-%02d-%s',substr(text,6,9),month,substr(text,1,2))
 d <- as.Date(iso);stopifnot(!is.na(d),format(d,'%Y-%m-%d')==iso);as.numeric(d-epoch)
}
read_data <- function(texts,i,payload) {
 name <- tolower(sub('^data[[:space:]]+','',texts[i],ignore.case=TRUE))
 stopifnot(tolower(texts[i+1L])=='infile cards',tolower(texts[i+3L])=='cards',tolower(texts[i+4L])=='run')
 remain <- sub('^input[[:space:]]+','',texts[i+2L],ignore.case=TRUE);schema <- list();reads <- list()
 while(nchar(trimws(remain))) {
  m <- regmatches(remain,regexec('^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)(?:[[:space:]]*:[[:space:]]*(?:\\$([0-9]+)\\.|(date9)\\.))?(?=[[:space:]]|$)',remain,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==4L)
  col <- tolower(m[2]);kind <- if(nzchar(m[3])) 'character' else if(nzchar(m[4])) 'date' else 'number';width <- if(kind=='character') as.integer(m[3]) else 8L
  schema[[col]] <- list(type=if(kind=='character') 'character' else 'number',length=width);reads[[col]] <- kind;remain <- substring(remain,nchar(m[1])+1L)
 }
 rows <- lapply(payload$records,function(record) {
  tokens <- strsplit(trimws(record),'[[:space:]]+')[[1]];stopifnot(length(tokens)==length(reads));row <- list()
  for(k in seq_along(reads)) {
   col <- names(reads)[k];kind <- reads[[k]];value <- if(kind=='character') paste0(tokens[k],strrep(' ',schema[[col]]$length-nchar(tokens[k]))) else if(kind=='date') read_date(tokens[k]) else if(tokens[k]=='.') NULL else as.numeric(tokens[k])
   row[col] <- list(value)
  }
  row
 })
 list(name=name,table=list(schema=schema,rows=rows))
}
parse_function <- function(block) {
 m <- regmatches(block[1],regexec('^function[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\([[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\)[[:space:]]*\\$[[:space:]]*9$',block[1],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 d <- regmatches(block[2],regexec("^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*intnx\\([[:space:]]*'week\\.([27])'[[:space:]]*,[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*,[[:space:]]*([01])[[:space:]]*\\)[[:space:]]*(?:-[[:space:]]*(1))?$",block[2],ignore.case=TRUE,perl=TRUE))[[1]]
 stopifnot(length(d)==6L,tolower(d[4])==tolower(m[3]));anchor <- as.integer(d[3]);offset <- as.integer(d[5]);adjust <- if(nzchar(d[6])) -1L else 0L
 stopifnot((anchor==2L && offset==0L && adjust==0L)||(anchor==7L && offset==1L && adjust== -1L))
 expected <- paste0('^return[[:space:]]*\\([[:space:]]*put\\([[:space:]]*',d[2],'[[:space:]]*,[[:space:]]*date9\\.[[:space:]]*\\)[[:space:]]*\\)$')
 stopifnot(grepl(expected,block[3],ignore.case=TRUE,perl=TRUE),tolower(block[4])=='endsub')
 list(name=tolower(m[2]),body=list(anchor=anchor,offset=offset,adjust=adjust))
}
callback <- function(value,body) {
 if(is.null(value)) return('.')
 date <- epoch+value;wday <- as.POSIXlt(date,tz='UTC')$wday;target <- body$anchor-1L
 back <- if(wday>=target) wday-target else wday+7L-target
 result <- date-back+body$offset*7L+body$adjust;stopifnot(as.integer(format(result,'%Y'))>=1753L,as.integer(format(result,'%Y'))<=3999L)
 toupper(format(result,'%d%b%Y'))
}
parse_columns <- function(text) {
 m <- regmatches(text,regexec("(?s)^columns?[[:space:]]+(.+)[[:space:]]*\\([[:space:]]*('(?:[^']|'')*')[[:space:]]+(.+)\\)$",text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==4L)
 span <- gsub("''","'",substr(m[3],2,nchar(m[3])-1),fixed=TRUE);result <- list()
 for(k in c(2L,4L)) for(token in strsplit(trimws(m[k]),'[[:space:]]+')[[1]]) {
  pair <- strsplit(tolower(token),'=',fixed=TRUE)[[1]];stopifnot(length(pair)%in%c(1L,2L));result[[length(result)+1L]] <- list(source=pair[1],alias=tail(pair,1),span=if(k==2L) NULL else span)
 }
 result
}
parse_define <- function(text) {
 m <- regmatches(text,regexec('(?s)^define[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*/[[:space:]]*(.*)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 spec <- list(display=FALSE,order=FALSE,format=NULL,label=NULL)
 for(token in regmatches(m[3],gregexpr("'(?:[^']|'')*'|[^[:space:]]+",m[3],perl=TRUE))[[1]]) {
  norm <- tolower(token)
  if(norm %in% c('order','display')) spec[[norm]] <- TRUE else if(startsWith(norm,'format=')) spec$format <- substr(norm,8,nchar(norm)-1L) else if(startsWith(token,"'")) spec$label <- gsub("''","'",substr(token,2,nchar(token)-1),fixed=TRUE) else stop('unknown independent REPORT option')
 }
 list(name=tolower(m[2]),spec=spec)
}
texts <- vapply(statements,function(s)s$text,'');norm <- tolower(gsub('[[:space:]]+',' ',texts));payloads <- Filter(function(e)e$kind=='opaque_data',events)
tables <- list();functions <- list();formats <- list();reports <- list();trace <- list();title <- NULL;library <- NULL;active <- NULL;i <- 1L;pi <- 1L;steps <- 0L;inputs <- 0L;producers <- 0L;titles <- 0L;calls <- 0L
add <- function(value) trace[[length(trace)+1L]] <<- value
while(i<=length(texts)) {
 if(startsWith(norm[i],'proc fcmp ')) {
  m <- regmatches(texts[i],regexec('^proc[[:space:]]+fcmp[[:space:]]+outlib[[:space:]]*=[[:space:]]*(work\\.functions)\\.([A-Za-z_][A-Za-z0-9_]*)$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
  library <- tolower(m[2]);package <- tolower(m[3]);i <- i+1L;count <- 0L
  while(startsWith(norm[i],'function ')) {
   fn <- parse_function(texts[i:(i+3L)]);stopifnot(is.null(functions[[fn$name]]));functions[[fn$name]] <- fn$body;count <- count+1L
   add(paste('week_function',fn$name,fn$body$anchor,fn$body$offset,fn$body$adjust,sep='|'));i <- i+4L
  }
  stopifnot(norm[i]=='quit');add(paste('week_library',library,package,count,sep='|'));i <- i+1L;steps <- steps+1L
 } else if(startsWith(norm[i],'options ')) {
  m <- regmatches(texts[i],regexec('^options[[:space:]]+cmplib[[:space:]]*=[[:space:]]*(work\\.functions)$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==2L,tolower(m[2])==library)
  active <- library;add(paste('week_cmplib',active,sep='|'));i <- i+1L;steps <- steps+1L
 } else if(norm[i]=='proc format') {
  stopifnot(active==library);i <- i+1L
  while(startsWith(norm[i],'value ')) {
   m <- regmatches(texts[i],regexec('^value[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+other[[:space:]]*=[[:space:]]*\\[[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\\([[:space:]]*\\)[[:space:]]*\\]$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L,!is.null(functions[[tolower(m[3])]]))
   name <- tolower(m[2]);formats[[name]] <- tolower(m[3]);add(paste('week_format',name,formats[[name]],sep='|'));i <- i+1L;steps <- steps+1L
  }
  stopifnot(norm[i]=='run');i <- i+1L
 } else if(startsWith(norm[i],'data ')) {
  value <- read_data(texts,i,payloads[[pi]]);pi <- pi+1L;tables[[value$name]] <- value$table
  for(j in seq_along(value$table$rows)) {add(paste('week_input',value$name,j,1,sep='|'));add(paste('week_output',value$name,j,sep='|'))}
  add(paste('week_input',value$name,length(value$table$rows)+1L,0,sep='|'));inputs <- inputs+as.integer(length(value$table$rows));producers <- producers+1L;i <- i+5L;steps <- steps+1L
 } else if(startsWith(norm[i],'proc report ')) {
  m <- regmatches(texts[i],regexec('^proc[[:space:]]+report[[:space:]]+data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+nowd$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==2L);name <- tolower(m[2]);i <- i+1L
  cols <- parse_columns(texts[i]);defs <- list();i <- i+1L
  while(startsWith(norm[i],'define ')) {value <- parse_define(texts[i]);defs[[value$name]] <- value$spec;i <- i+1L}
  if(grepl('^title([[:space:]]|$)',norm[i])) {
   title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'(.*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L;i <- i+1L
   add(if(is.null(title)) 'week_title|reset' else paste0('week_title|set|',hex(title)))
  }
  stopifnot(norm[i]=='run');i <- i+1L;steps <- steps+1L;ordinal <- as.integer(length(reports)+1L);table <- tables[[name]]
  header <- paste(vapply(cols,function(col) {label <- defs[[col$alias]]$label;if(is.null(label))label <- col$alias;json_string(paste0(if(is.null(col$span)) '' else paste0(col$span,'/'),label))},''),collapse=' ')
  lines <- if(is.null(title)) character() else paste0('TITLE: ',title);lines <- c(lines,header);previous <- NULL
  add(paste('week_report',name,ordinal,length(table$rows),sep='|'));add(paste0('week_header|',hex(header)))
  for(j in seq_along(table$rows)) {
   row <- table$rows[[j]];cells <- character()
   for(col in cols) {
    value <- row[[col$source]];spec <- defs[[col$alias]];fmt <- spec$format
    if(isTRUE(spec$order)) {token <- json_string(if(!is.null(previous)&&value==previous) '' else integer_text(value));previous <- value
    } else if(!is.null(fmt)&&fmt=='weekdate') {
     if(is.null(value)) label <- '.' else {d <- epoch+value;label <- paste0(format(d,'%A, %B '),as.integer(format(d,'%d')),format(d,', %Y'))};token <- json_string(label)
    } else if(!is.null(fmt)&&endsWith(fmt,'12')) {
     key <- substr(fmt,1,nchar(fmt)-2L);fn <- formats[[key]];label <- callback(value,functions[[fn]]);token <- json_string(label);calls <- calls+1L
     add(paste0('week_callback|',fn,'|',if(is.null(value)) '.' else integer_text(value),'|',hex(label)))
    } else if(!is.null(fmt)&&fmt=='10') token <- json_string(if(is.null(value)) '.' else integer_text(value)) else if(table$schema[[col$source]]$type=='character') token <- json_string(sub(' +$','',value)) else token <- if(is.null(value)) '.' else integer_text(value)
    cells <- c(cells,token)
   }
   line <- paste(cells,collapse=' ');lines <- c(lines,line);add(paste0('week_report_row|',ordinal,'|',j,'|',hex(line)))
  }
  key <- sprintf('report_%02d.txt',ordinal);reports[[key]] <- paste0(paste(lines,collapse='\n'),'\n');add(paste('week_artifact',key,nchar(reports[[key]],type='bytes'),sep='|'))
 } else if(grepl('^title([[:space:]]|$)',norm[i])) {
  title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'(.*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L;steps <- steps+1L;i <- i+1L
  add(if(is.null(title)) 'week_title|reset' else paste0('week_title|set|',hex(title)))
 } else stop('unconsumed independent callback source')
}
result <- list(datasets=tables,log=list());if(length(reports))result$reports <- reports
accounting <- list(language_statements=as.integer(length(statements)),opaque_payloads=producers,steps=steps,input_records=inputs,input_attempts=inputs+producers,functions=as.integer(length(functions)),formats=as.integer(length(formats)),callback_calls=calls,title_sets=titles,reports=as.integer(length(reports)),statement_lines=lapply(statements,function(s)as.integer(s$line)))
dir.create(output_path,recursive=TRUE);write_json('result.json',result);write_json('accounting.json',accounting);write_json('trace.json',trace)
