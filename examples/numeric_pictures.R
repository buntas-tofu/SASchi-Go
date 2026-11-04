# Independent whole-source integer PICTURE, fixed input and detail REPORT witness.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2L,!file.exists(args[2]))
input_path <- args[1];output_path <- args[2]
con <- file(input_path,open='rb');original_raw <- readBin(con,'raw',n=file.info(input_path)$size);close(con)
bom <- length(original_raw)>=3L && identical(original_raw[1:3],as.raw(c(239,187,191)))
if(bom) {prepared <- tempfile('numeric-picture-ascii-');writeBin(original_raw[-(1:3)],prepared);input_path <- prepared}
script <- sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1]);common <- file.path(dirname(normalizePath(script)),'format_oracle_common.R')
if(!file.exists(common)) common <- file.path('examples','format_oracle_common.R')
source(common)
valid_template <- function(text,noedit) {
 stopifnot(nchar(text,type='bytes')>=1L,nchar(text,type='bytes')<=40L,nzchar(trimws(text)),all(utf8ToInt(text)>=32L & utf8ToInt(text)<=126L),!grepl('[%&]',text))
 if(noedit || !grepl('[0-9]',text)) return(invisible(TRUE))
 stopifnot(grepl('^[0-9]{1,16}[A-Za-z ]*$',text),grepl('[1-9]',sub('[A-Za-z ].*$','',text)))
}
parse_picture <- function(text) {
 head <- regmatches(text,regexec('(?s)^picture[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+(.+)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(head)==3L)
 remain <- head[3];entries <- list();previous <- -2147483648
 pattern <- "^[[:space:]]*(low|[+-]?[0-9]+)(?:[[:space:]]*(<)?[[:space:]]*-[[:space:]]*(<)?[[:space:]]*(high|[+-]?[0-9]+))?[[:space:]]*=[[:space:]]*('(?:[^']|'')*')[[:space:]]*(\\([[:space:]]*noedit[[:space:]]*\\))?"
 while(nchar(trimws(remain))) {
  m <- regmatches(remain,regexec(pattern,remain,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==7L)
  stopifnot(!(tolower(m[2])=='low' && (nzchar(m[3]) || !nzchar(m[5]))),!(tolower(m[5])=='high' && nzchar(m[4])))
  lo <- (if(tolower(m[2])=='low') -2147483647 else as.numeric(m[2]))+as.integer(nzchar(m[3]))
  hi <- (if(!nzchar(m[5])) lo else if(tolower(m[5])=='high') 2147483647 else as.numeric(m[5]))-as.integer(nzchar(m[4]))
  text <- gsub("''","'",substr(m[6],2,nchar(m[6])-1),fixed=TRUE);noedit <- nzchar(m[7]);valid_template(text,noedit)
  stopifnot(lo==previous+1,lo<=hi,lo>=-2147483647,hi<=2147483647)
  entries[[length(entries)+1L]] <- list(lower=lo,upper=hi,text=text,noedit=noedit);previous <- hi;remain <- substring(remain,nchar(m[1])+1L)
 }
 stopifnot(previous==2147483647);list(name=tolower(head[2]),entries=entries)
}
edited <- function(value,text,noedit) {
 if(noedit || !grepl('[0-9]',text)) return(text)
 m <- regmatches(text,regexec('^([0-9]+)(.*)$',text,perl=TRUE))[[1]];selectors <- strsplit(m[2],'',fixed=TRUE)[[1]];width <- length(selectors)
 number <- integer_text(abs(value));digits <- strsplit(paste0(strrep('0',max(0L,width-nchar(number))),number),'',fixed=TRUE)[[1]];digits <- tail(digits,width)
 kept <- FALSE;out <- character(width)
 for(j in seq_len(width)) {
  if(kept || selectors[j]!='0' || digits[j]!='0') {kept <- TRUE;out[j] <- digits[j]} else out[j] <- ' '
 }
 paste0(sub('^ +','',paste0(out,collapse='')),m[3])
}
display <- function(value,entries) {
 for(item in entries) if(value>=item$lower && value<=item$upper) return(edited(value,item$text,item$noedit))
 stop('uncovered numeric picture value')
}
columns <- function(text) {
 tokens <- strsplit(tolower(sub('^columns?[[:space:]]+','',text,ignore.case=TRUE)),'[[:space:]]+')[[1]]
 lapply(tokens,function(token) {parts <- strsplit(token,'=',fixed=TRUE)[[1]];list(source=parts[1],alias=tail(parts,1))})
}
define <- function(text) {
 m <- regmatches(text,regexec('(?s)^define[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*/[[:space:]]*(.*)$',text,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==3L)
 tokens <- regmatches(m[3],gregexpr("'(?:[^']|'')*'|[^[:space:]]+",m[3],perl=TRUE))[[1]];fmt <- NULL;label <- NULL;is_display <- FALSE
 for(token in tokens) {
  if(tolower(token)=='display') is_display <- TRUE else if(startsWith(tolower(token),'format=')) fmt <- tolower(substr(token,8,nchar(token)-1)) else if(startsWith(token,"'")) label <- gsub("''","'",substr(token,2,nchar(token)-1),fixed=TRUE) else stop('report definition')
 }
 list(name=tolower(m[2]),spec=list(display=is_display,format=fmt,label=label))
}
texts <- vapply(statements,function(s)s$text,'');norm <- tolower(gsub('[[:space:]]+',' ',texts));payloads <- Filter(function(e)e$kind=='opaque_data',events)
tables <- list();formats <- list();reports <- list();trace <- list(paste0('numeric_picture_prefix|',if(bom) 'utf8-bom' else 'none','|',if(bom) 3L else 0L));title <- NULL
i <- 1L;pi <- 1L;steps <- 0L;inputs <- 0L;producers <- 0L;titles <- 0L
add <- function(value) trace[[length(trace)+1L]] <<- value
while(i<=length(texts)) {
 if(startsWith(norm[i],'data ')) {
  name <- sub('^data[[:space:]]+','',norm[i]);stopifnot(norm[i+1L]=='infile datalines',norm[i+3L]=='datalines',norm[i+4L]=='run')
  m <- regmatches(texts[i+2L],regexec('^input[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+\\$([1-8])\\.$',texts[i+2L],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==4L)
  number <- tolower(m[2]);character_name <- tolower(m[3]);width <- as.integer(m[4]);schema <- list();schema[[number]] <- list(type='number',length=8L);schema[[character_name]] <- list(type='character',length=width)
  payload <- payloads[[pi]];pi <- pi+1L;rows <- list()
  for(j in seq_along(payload$records)) {
   record <- payload$records[j];v <- regmatches(record,regexec(paste0('^([+-]?[0-9]{1,10}) ([A-Za-z]{',width,'})( *)$'),record,perl=TRUE))[[1]]
   stopifnot(length(v)==4L,nchar(record,type='bytes')<=80L,abs(as.numeric(v[2]))<=2147483647)
   row <- list();row[[number]] <- as.numeric(v[2]);row[[character_name]] <- v[3];rows[[j]] <- row
   add(paste('number_input',name,j,1,sep='|'));add(paste('number_output',name,j,sep='|'))
  }
  add(paste('number_input',name,length(rows)+1L,0,sep='|'));tables[[name]] <- list(schema=schema,rows=rows);inputs <- inputs+as.integer(length(rows));producers <- producers+1L;steps <- steps+1L;i <- i+5L
 } else if(norm[i]=='proc format') {
  i <- i+1L
  while(startsWith(norm[i],'picture ')) {entry <- parse_picture(texts[i]);formats[[entry$name]] <- entry$entries;add(paste('number_picture',entry$name,length(entry$entries),sep='|'));steps <- steps+1L;i <- i+1L}
  stopifnot(norm[i]=='run');i <- i+1L
 } else if(startsWith(norm[i],'proc report ')) {
  name <- sub('^proc report data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+nowd$','\\1',norm[i]);i <- i+1L
  cols <- columns(texts[i]);definitions <- list();i <- i+1L
  while(startsWith(norm[i],'define ')) {entry <- define(texts[i]);definitions[[entry$name]] <- entry$spec;i <- i+1L}
  if(startsWith(norm[i],'title')) {
   title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'((?:[^']|'')*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L
   add(if(is.null(title)) 'number_title|reset' else paste0('number_title|set|',hex(title)));i <- i+1L
  }
  stopifnot(norm[i]=='run');i <- i+1L
  header <- paste(vapply(cols,function(col)json_string(if(is.null(definitions[[col$alias]]$label)) col$alias else definitions[[col$alias]]$label),''),collapse=' ')
  lines <- c(if(is.null(title)) character() else paste0('TITLE: ',title),header);ordinal <- length(reports)+1L
  add(paste('number_report',name,ordinal,length(tables[[name]]$rows),sep='|'));add(paste0('number_header|',hex(header)))
  for(j in seq_along(tables[[name]]$rows)) {
   row <- tables[[name]]$rows[[j]];line <- paste(vapply(cols,function(col) {
    value <- row[[col$source]];fmt <- definitions[[col$alias]]$format
    if(!is.null(fmt)) json_string(if(fmt=='comma12') formatC(value,format='d',big.mark=',') else display(value,formats[[fmt]])) else if(tables[[name]]$schema[[col$source]]$type=='character') json_string(sub(' +$','',value)) else integer_text(value)
   },''),collapse=' ')
   lines <- c(lines,line);add(paste0('number_report_row|',ordinal,'|',j,'|',hex(line)))
  }
  key <- sprintf('report_%02d.txt',ordinal);reports[[key]] <- paste0(paste(lines,collapse='\n'),'\n');add(paste0('number_artifact|',key,'|',nchar(reports[[key]],type='bytes')));steps <- steps+1L
 } else if(norm[i]=='title' || startsWith(norm[i],'title ')) {
  title <- if(norm[i]=='title') NULL else gsub("''","'",sub("^title[[:space:]]+'((?:[^']|'')*)'$",'\\1',texts[i],ignore.case=TRUE,perl=TRUE),fixed=TRUE);titles <- titles+1L;steps <- steps+1L;i <- i+1L
  add(if(is.null(title)) 'number_title|reset' else paste0('number_title|set|',hex(title)))
 } else stop('unconsumed numeric picture source')
}
result <- list(datasets=tables,log=list());if(length(reports)) result$reports <- reports
accounting <- list(language_statements=as.integer(length(statements)),opaque_payloads=producers,steps=steps,input_records=inputs,input_attempts=inputs+producers,
 picture_definitions=as.integer(length(formats)),title_sets=titles,reports=as.integer(length(reports)),source_prefix_bytes=if(bom) 3L else 0L,statement_lines=as.list(vapply(statements,function(s)s$line,1L)))
dir.create(output_path,recursive=TRUE);write_json('result.json',result);write_json('accounting.json',accounting);write_json('trace.json',trace)
