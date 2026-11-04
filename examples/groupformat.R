# Independent source-reading numeric GROUPFORMAT and detail REPORT witness.
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
parse_value <- function(text) {
 m <- regmatches(text,regexec('(?s)^value[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+(.+)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 remain <- m[3];entries <- list()
 while(nchar(trimws(remain))) {
  part <- regmatches(remain,regexec("^[[:space:]]*(low|[+-]?[0-9]+)[[:space:]]*-[[:space:]]*(<)?[[:space:]]*(high|[+-]?[0-9]+)[[:space:]]*=[[:space:]]*('(?:[^']|'')*')",remain,ignore.case=TRUE,perl=TRUE))[[1]]
  stopifnot(length(part)==5L)
  entries[[length(entries)+1L]] <- list(lower=if(tolower(part[2])=='low') -2147483647 else as.numeric(part[2]),upper=(if(tolower(part[4])=='high') 2147483647 else as.numeric(part[4]))-as.integer(nzchar(part[3])),text=gsub("''","'",substr(part[5],2,nchar(part[5])-1),fixed=TRUE))
  remain <- substring(remain,nchar(part[1])+1L)
 }
 list(name=tolower(m[2]),entries=entries)
}
formatted <- function(value,definition) {
 if(is.null(value)) return('.')
 for(item in definition) if(value>=item$lower && value<=item$upper) return(item$text)
 stop('uncovered independent numeric value')
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
parse_columns <- function(text) {
 tokens <- strsplit(tolower(sub('^columns?[[:space:]]+','',text,ignore.case=TRUE)),'[[:space:]]+')[[1]]
 lapply(tokens,function(token) {parts <- strsplit(token,'=',fixed=TRUE)[[1]];stopifnot(length(parts)%in%c(1L,2L));list(source=parts[1],alias=tail(parts,1))})
}
parse_define <- function(text) {
 m <- regmatches(text,regexec('(?s)^define[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*/[[:space:]]*(.*)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 tokens <- regmatches(m[3],gregexpr("'(?:[^']|'')*'|[^[:space:]]+",m[3],perl=TRUE))[[1]];fmt <- NULL;label <- NULL;display <- FALSE
 for(token in tokens) {
  if(tolower(token)=='display') display <- TRUE else if(startsWith(tolower(token),'format=')) fmt <- tolower(substr(token,8,nchar(token)-1)) else if(startsWith(token,"'")) label <- gsub("''","'",substr(token,2,nchar(token)-1),fixed=TRUE) else stop('hand REPORT option')
 }
 list(name=tolower(m[2]),spec=list(display=display,format=fmt,label=label))
}
cell <- function(value,spec,fmt,formats) {
 if(!is.null(fmt)) {
  if(fmt=='date9') return(json_string(if(is.null(value)) '.' else toupper(format(epoch+value,'%d%b%Y'))))
  if(fmt=='dollar12') return(json_string(if(is.null(value)) '.' else paste0('$',formatC(value,format='d',big.mark=','))))
  return(json_string(formatted(value,formats[[fmt]])))
 }
 if(spec$type=='character') return(json_string(sub(' +$','',value)))
 if(is.null(value)) '.' else integer_text(value)
}
texts <- vapply(statements,function(s)s$text,'');norm <- tolower(gsub('[[:space:]]+',' ',texts));payloads <- Filter(function(e)e$kind=='opaque_data',events)
tables <- list();formats <- list();reports <- list();trace <- list();title <- NULL;i <- 1L;pi <- 1L;steps <- 0L;inputs <- 0L;producers <- 0L;titles <- 0L;groups <- 0L;outputs <- 0L
add <- function(value) trace[[length(trace)+1L]] <<- value
while(i<=length(texts)) {
 if(norm[i]=='proc format') {
  value <- parse_value(texts[i+1L]);stopifnot(norm[i+2L]=='run');formats[[value$name]] <- value$entries
  add(paste('numeric_value',value$name,length(value$entries),sep='|'));i <- i+3L
 } else if(startsWith(norm[i],'data ') && norm[i+1L]=='infile cards') {
  value <- read_data(texts,i,payloads[[pi]]);pi <- pi+1L;tables[[value$name]] <- value$table
  for(j in seq_along(value$table$rows)) {add(paste('group_input',value$name,j,1,sep='|'));add(paste('group_output',value$name,j,sep='|'))}
  add(paste('group_input',value$name,length(value$table$rows)+1L,0,sep='|'));inputs <- inputs+as.integer(length(value$table$rows));producers <- producers+1L;i <- i+5L
 } else if(startsWith(norm[i],'data ')) {
  name <- sub('^data[[:space:]]+','',norm[i]);previous <- sub('^set[[:space:]]+','',norm[i+1L]);key <- sub('^by[[:space:]]+groupformat[[:space:]]+','',norm[i+2L])
  binding <- strsplit(sub('^format[[:space:]]+','',norm[i+3L]),'[[:space:]]+')[[1]];stopifnot(binding[1]==key);fmt <- sub('\\.$','',binding[2])
  stopifnot(norm[i+4L]==paste0('if first.',key,' then output'),norm[i+5L]==paste0('if last.',key,' then output'),norm[i+6L]=='run')
  original <- tables[[previous]];rows <- original$rows;labels <- vapply(rows,function(row)formatted(row[[key]],formats[[fmt]]),'');result <- list()
  add(paste('groupformat_begin',name,previous,key,fmt,sep='|'))
  for(j in seq_along(rows)) {
   first <- j==1L || labels[j]!=labels[j-1L];last <- j==length(rows) || labels[j]!=labels[j+1L]
   add(paste('groupformat_row',j,as.integer(first),as.integer(last),hex(labels[j]),sep='|'))
   if(first) {result[[length(result)+1L]] <- rows[[j]];add(paste('groupformat_output','first',j,sep='|'))}
   if(last) {result[[length(result)+1L]] <- rows[[j]];add(paste('groupformat_output','last',j,sep='|'))}
  }
  tables[[name]] <- list(schema=original$schema,rows=result);add(paste('groupformat_end',name,length(result),sep='|'));groups <- groups+1L;outputs <- outputs+as.integer(length(result));i <- i+7L
 } else if(startsWith(norm[i],'proc report ')) {
  name <- sub('^proc report data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+nowd$','\\1',norm[i]);i <- i+1L
  columns <- parse_columns(texts[i]);definitions <- list();i <- i+1L
  while(startsWith(norm[i],'define ')) {entry <- parse_define(texts[i]);definitions[[entry$name]] <- entry$spec;i <- i+1L}
  if(startsWith(norm[i],'title')) {
   title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'((?:[^']|'')*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L
   add(if(is.null(title)) 'group_title|reset' else paste0('group_title|set|',hex(title)));i <- i+1L
  }
  stopifnot(norm[i]=='run');i <- i+1L
  header <- paste(vapply(columns,function(col)json_string(if(is.null(definitions[[col$alias]]$label)) col$alias else definitions[[col$alias]]$label),''),collapse=' ')
  lines <- c(if(is.null(title)) character() else paste0('TITLE: ',title),header);ordinal <- length(reports)+1L
  add(paste('group_report',name,ordinal,length(tables[[name]]$rows),sep='|'));add(paste0('group_header|',hex(header)))
  for(j in seq_along(tables[[name]]$rows)) {
   row <- tables[[name]]$rows[[j]];line <- paste(vapply(columns,function(col)cell(row[[col$source]],tables[[name]]$schema[[col$source]],definitions[[col$alias]]$format,formats),''),collapse=' ')
   lines <- c(lines,line);add(paste0('group_report_row|',ordinal,'|',j,'|',hex(line)))
  }
  filename <- sprintf('report_%02d.txt',ordinal);reports[[filename]] <- paste0(paste(lines,collapse='\n'),'\n');add(paste0('group_artifact|',filename,'|',nchar(reports[[filename]],type='bytes')))
 } else if(norm[i]=='title' || startsWith(norm[i],'title ')) {
  title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'((?:[^']|'')*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L
  add(if(is.null(title)) 'group_title|reset' else paste0('group_title|set|',hex(title)));i <- i+1L
 } else stop('unconsumed R GROUPFORMAT source')
 steps <- steps+1L
}
result <- list(datasets=tables,log=list());if(length(reports)) result$reports <- reports
accounting <- list(language_statements=as.integer(length(statements)),opaque_payloads=producers,steps=steps,input_records=inputs,input_attempts=inputs+producers,
 group_steps=groups,explicit_outputs=outputs,title_sets=titles,reports=as.integer(length(reports)),statement_lines=as.list(vapply(statements,function(s)s$line,1L)))
dir.create(output_path,recursive=TRUE);write_json('result.json',result);write_json('accounting.json',accounting);write_json('trace.json',trace)
