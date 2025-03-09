$(document).ready(function(){
console.log( "Page Is Ready" );

    $(document).keypress(function(e) {

      if(event.which == 115) {
       $("#mainWord").addClass('text-secondary');
            $.post( "/lessonplans/grade", {
                grade: "sloth",
            })
            .done(function( data ) {
                console.log( data );
            });
      }

      if(event.which == 100) {
        $("#mainWord").addClass('text-secondary');
        alert('deer');
      }
      if(event.which == 102) {
        $("#mainWord").addClass('text-secondary');
        alert('falcon');
      }
    });
});

function changeVisibility() {
    $("#mainWord").toggle(0);
    $("#mainWord").addClass('text-primary');
    console.log( "Change Visibility Function Ran" );
}

function makeVisible() {
    $("#mainWord").show();
    $("#mainWord").removeClass('text-primary');
    console.log( "Make Visible Function Ran" );
}